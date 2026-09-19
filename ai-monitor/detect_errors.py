import re
import sys

# Match an HTTP 404 response in an Nginx access-log line.
HTTP_404 = re.compile(
    r'"[A-Z]+ [^"]+ HTTP/\d(?:\.\d)?"\s+404\s'
)


def main():
    logs = sys.stdin.read()

    if not logs.strip():
        print("No log input received; detection was not performed.")
        return

    matches = [
        line for line in logs.splitlines()
        if HTTP_404.search(line)
    ]

    if not matches:
        print("No HTTP 404 matches in the supplied logs.")
        print("Other errors have not been checked yet.")
        return

    print("Rule: nginx_http_404")
    print("Category: HTTP resource not found")
    print("Severity: LOW")
    print(f"Matched requests: {len(matches)}")
    print("Confirmed evidence: Nginx returned HTTP 404.")
    print("Possible cause: Missing resource or incorrect request path.")
    print("Suggested check: Verify the requested URL and routing.")
    print("Evidence:")

    for line in matches[-3:]:
        print(line)


if __name__ == "__main__":
    main()
