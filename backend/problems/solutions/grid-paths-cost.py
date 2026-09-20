import sys


def main():
    data = sys.stdin.buffer.read().split()
    r, c = int(data[0]), int(data[1])
    values = [int(x) for x in data[2:2 + r * c]]

    # One row of state, updated in place: reaching a cell only ever depends on the cell
    # above (the previous value of row[j]) and the cell left (the new row[j-1]).
    row = [0] * c
    for i in range(r):
        for j in range(c):
            cell = values[i * c + j]
            if i == 0 and j == 0:
                row[j] = cell
            elif i == 0:
                row[j] = row[j - 1] + cell
            elif j == 0:
                row[j] = row[j] + cell
            else:
                row[j] = min(row[j], row[j - 1]) + cell
    print(row[c - 1])


main()
