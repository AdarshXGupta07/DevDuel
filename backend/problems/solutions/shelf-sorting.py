import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    grades = [int(x) for x in data[1:1 + n]]

    # Dutch national flag: low marks the end of the 0s, high the start of the 2s.
    low, mid, high = 0, 0, n - 1
    while mid <= high:
        if grades[mid] == 0:
            grades[low], grades[mid] = grades[mid], grades[low]
            low += 1
            mid += 1
        elif grades[mid] == 1:
            mid += 1
        else:
            grades[mid], grades[high] = grades[high], grades[mid]
            high -= 1

    sys.stdout.write(" ".join(map(str, grades)))


main()
