import sys


def main():
    data = sys.stdin.buffer.read().split()
    n, start = int(data[0]), int(data[1])
    nxt = [int(x) for x in data[2:2 + n]]

    def step(node: int) -> int:
        return nxt[node] if node != -1 else -1

    # Floyd: the fast walker laps the slow one inside a loop, and falls off the end if
    # there isn't one. O(1) space — no visited set.
    slow = start
    fast = start
    while True:
        slow = step(slow)
        fast = step(step(fast))
        if fast == -1 or slow == -1:
            print("TERMINATES")
            return
        if slow == fast:
            print("LOOP")
            return


main()
