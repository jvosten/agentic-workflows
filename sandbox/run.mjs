// Run one guest script in a Gondolin VM: the network allows only GitHub, the guest gets GH_TOKEN as a placeholder.
//
//   node run.mjs [--allow-host HOST]... [--mirror DIR] [--inbox DIR] [--resume CKPT] [--checkpoint CKPT] SCRIPT [ARG...]
//
// SCRIPT is a file under guest/, run with a login shell; it sees guest/ read-only at /sandbox/guest and, with
// --mirror and --inbox, a host mirror at /sandbox/mirror and a change to carry at /sandbox/inbox, read-only.
// --allow-host adds a host to github.com and api.github.com (a package index for verify). GH_TOKEN, GIT_NAME and GIT_EMAIL come from the host environment;
// GH_TOKEN never enters the guest. --checkpoint writes the root disk after the script and stops the VM;
// --resume boots from such a checkpoint instead of the image (GONDOLIN_GUEST_DIR selects the image).
import path from "node:path";
import { parseArgs } from "node:util";
import {
  VM,
  VmCheckpoint,
  RealFSProvider,
  ReadonlyProvider,
  createHttpHooks,
} from "@earendil-works/gondolin";

const here = path.dirname(new URL(import.meta.url).pathname);
const { values: opts, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    "allow-host": { type: "string", multiple: true, default: [] },
    mirror: { type: "string" },
    inbox: { type: "string" },
    resume: { type: "string" },
    checkpoint: { type: "string" },
  },
});
const [script, ...args] = positionals;
if (!script) {
  console.error("usage: node run.mjs [--allow-host HOST]... [--mirror DIR] [--inbox DIR] [--resume CKPT] [--checkpoint CKPT] SCRIPT [ARG...]");
  process.exit(2);
}
for (const name of ["GH_TOKEN", "GIT_NAME", "GIT_EMAIL"]) {
  if (!process.env[name]) {
    console.error(`run.mjs: ${name} is not set`);
    process.exit(2);
  }
}

const github = ["github.com", "api.github.com"];
const { httpHooks, env } = createHttpHooks({
  allowedHosts: [...github, ...opts["allow-host"]],
  secrets: { GH_TOKEN: { hosts: github, value: process.env.GH_TOKEN } },
});
const mounts = { "/sandbox/guest": new ReadonlyProvider(new RealFSProvider(path.join(here, "guest"))) };
if (opts.mirror) {
  mounts["/sandbox/mirror"] = new ReadonlyProvider(new RealFSProvider(path.resolve(opts.mirror)));
}
if (opts.inbox) {
  mounts["/sandbox/inbox"] = new ReadonlyProvider(new RealFSProvider(path.resolve(opts.inbox)));
}
const vmOptions = {
  httpHooks,
  env: { ...env, GIT_NAME: process.env.GIT_NAME, GIT_EMAIL: process.env.GIT_EMAIL },
  vfs: { mounts },
  rootfs: { mode: "cow", size: "4G" },
  sessionLabel: "aw-sandbox",
};

const t0 = performance.now();
const vm = opts.resume
  ? await VmCheckpoint.load(path.resolve(opts.resume)).resume(vmOptions)
  : await VM.create(vmOptions);
const booted = performance.now();
let code = 1;
try {
  const result = await vm.exec(["/bin/sh", "-l", `/sandbox/guest/${script}`, ...args], {
    stdout: process.stdout,
    stderr: process.stderr,
  });
  code = result.exitCode;
  if (opts.checkpoint && code === 0) {
    await vm.checkpoint(path.resolve(opts.checkpoint));
  }
} finally {
  await vm.close();
}
const done = performance.now();
console.error(`run.mjs: boot_s=${((booted - t0) / 1000).toFixed(1)} total_s=${((done - t0) / 1000).toFixed(1)} exit=${code}`);
process.exit(code);
