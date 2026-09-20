import sys
from collections import deque


def main():
    data = sys.stdin.buffer.read().split()
    r, c = int(data[0]), int(data[1])
    grid = [row.decode() for row in data[2:2 + r]]
    sr, sc = int(data[2 + r]), int(data[3 + r])

    if grid[sr][sc] == "#":
        print(0)
        return

    seen = [[False] * c for _ in range(r)]
    seen[sr][sc] = True
    queue = deque([(sr, sc)])
    flooded = 0

    while queue:
        row, col = queue.popleft()
        flooded += 1
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < r and 0 <= nc < c and not seen[nr][nc] and grid[nr][nc] == ".":
                seen[nr][nc] = True
                queue.append((nr, nc))

    print(flooded)


main()
