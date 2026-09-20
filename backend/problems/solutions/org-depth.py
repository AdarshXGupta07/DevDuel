import sys
from collections import deque


def main():
    data = sys.stdin.buffer.read().split()
    n = int(data[0])
    manager = [int(x) for x in data[1:1 + n]]

    children = [[] for _ in range(n)]
    root = 0
    for employee, boss in enumerate(manager):
        if boss == -1:
            root = employee
        else:
            children[boss].append(employee)

    # BFS by level rather than recursion: a 200k-deep chain would blow the Python stack,
    # and raising the recursion limit just moves the crash into the C stack.
    depth = 0
    queue = deque([root])
    while queue:
        depth += 1
        for _ in range(len(queue)):
            node = queue.popleft()
            queue.extend(children[node])
    print(depth)


main()
