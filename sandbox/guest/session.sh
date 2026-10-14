# A whole aw session in the guest, in two phases with a checkpoint between them (a session pauses for review):
#   session.sh open REPO TYPE SLUG   clone, aw start-task, carry the change in /sandbox/inbox, verify, commit, push,
#                                    open the merge request; leaves the worktree path in /work/session
#   session.sh finish                (resumed) wait for CI, then aw finish: merge, clean up
# /sandbox/inbox holds the change: tree/ (copied over the worktree), commit-msg, mr-title, mr-body.md.
. /sandbox/guest/setup.sh
case $1 in
  open)
    repo=$2 type=$3 slug=$4
    git clone -q "https://github.com/$repo.git" /work/repo
    cd /work/repo
    out=$(aw start-task "$type" "$slug")
    echo "$out"
    worktree=$(echo "$out" | sed -n 's/^worktree=//p')
    echo "$worktree" > /work/session
    cd "$worktree"
    cp -R /sandbox/inbox/tree/. .
    aw verify
    git add -A
    git commit -q -F /sandbox/inbox/commit-msg
    git log --stat --format='%h %s' -1
    git push -q -u origin HEAD
    aw mr create --title "$(cat /sandbox/inbox/mr-title)" --body-file /sandbox/inbox/mr-body.md
    ;;
  finish)
    cd "$(cat /work/session)"
    aw mr checks --watch
    aw mr view
    aw finish
    ;;
  *)
    echo "usage: session.sh open REPO TYPE SLUG | session.sh finish" >&2
    exit 2
    ;;
esac
