# Sourced in the guest: git identity, and git and gh authenticated with the GH_TOKEN placeholder.
# The guest never holds the real token: Gondolin swaps the placeholder in HTTP headers to the allowed hosts,
# Basic auth included, so git's credential helper can hand the placeholder over as the password.
set -eu
git config --global user.name "${GIT_NAME:?}"
git config --global user.email "${GIT_EMAIL:?}"
git config --global init.defaultBranch main
git config --global credential.https://github.com.helper \
  '!f() { echo username=x-access-token; echo "password=$GH_TOKEN"; }; f'
