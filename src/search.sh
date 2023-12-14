
set -e

depth=0

while [ $depth -lt 36 ]; do
    depth=$((depth + 1))
    echo DEPTH: $depth

    time python search_positions_faster.py --depth=${depth} --workers=2 | tee ${depth}-out.txt

done
