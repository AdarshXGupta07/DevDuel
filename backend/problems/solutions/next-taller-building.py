import sys


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    heights = [int(x) for x in data[1:1 + n]]

    answer = [-1] * n
    stack = []  # indices whose answer is still unknown, heights decreasing
    for i, h in enumerate(heights):
        while stack and heights[stack[-1]] < h:
            answer[stack.pop()] = h
        stack.append(i)

    sys.stdout.write(" ".join(map(str, answer)))


main()
