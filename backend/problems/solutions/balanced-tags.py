import sys


def main():
    line = sys.stdin.readline().strip()
    pairs = {")": "(", "]": "[", "}": "{"}
    stack = []
    for ch in line:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                print("INVALID")
                return
    print("VALID" if not stack else "INVALID")


main()
