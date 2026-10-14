# Start a session in the guest and time it: get the repository by MODE, then aw start-task docs SLUG.
#   fresh      clone from GitHub
#   reference  clone from GitHub, objects borrowed from the host mirror at /sandbox/mirror (read-only)
#   dissociate as reference, then copy the borrowed objects so the clone stands alone
#   warm       the clone is already in /work/repo (resumed checkpoint): fetch only
# SLUG - stops after the repository: a clone to time alone, or to checkpoint for warm starts.
# Usage: start.sh MODE REPO [SLUG]
. /sandbox/guest/setup.sh
mode=$1 repo=$2 slug=${3:-start-$1}
url="https://github.com/$repo.git"
now() { cut -d" " -f1 /proc/uptime; }
a=$(now)
case $mode in
  fresh) git clone -q "$url" /work/repo ;;
  reference) git clone -q --reference /sandbox/mirror "$url" /work/repo ;;
  dissociate) git clone -q --reference /sandbox/mirror --dissociate "$url" /work/repo ;;
  warm) git -C /work/repo fetch -q origin ;;
  *) echo "start.sh: unknown mode $mode" >&2; exit 2 ;;
esac
b=$(now)
echo "repo_s=$(awk "BEGIN{printf \"%.1f\", $b-$a}") mode=$mode"
[ "$slug" = - ] && exit 0
cd /work/repo
aw start-task docs "$slug"
c=$(now)
echo "start_task_s=$(awk "BEGIN{printf \"%.1f\", $c-$b}") total_s=$(awk "BEGIN{printf \"%.1f\", $c-$a}")"
