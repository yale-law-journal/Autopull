cd "$(dirname "$0")"
./pull_spreadsheet "$1" | sed 's/.*/&<br\/>/'
