cd "$(dirname "$0")"
./apply_perma "$1" | sed 's/.*/&<br\/>/'
