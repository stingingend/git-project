"""Exercise the Compose stack using only the Python standard library."""
import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--web", default="http://127.0.0.1:13000")
    parser.add_argument("--api", default="http://127.0.0.1:18001")
    parser.add_argument("--expect-existing", action="store_true")
    args = parser.parse_args()
    assert request(args.api + "/ready") == {"status": "ready"}
    assert request(args.web + "/api/ready") == {"status": "ready"}
    with urlopen(args.web, timeout=15) as response:
        assert "CodeAtlas" in response.read().decode()
    url = "https://github.com/example/compose-smoke"
    if not args.expect_existing:
        try:
            request(args.web + "/api/repositories", {"github_url": url})
        except HTTPError as exc:
            if exc.code != 409:
                raise
    repos = request(args.web + "/api/repositories")
    assert isinstance(request(args.web + "/api/jobs?limit=1"), list)
    assert any(repo["github_url"] == url for repo in repos), "Registered repository did not persist"
    print("Stack smoke check passed: web, proxy, API, PostgreSQL persistence.")


if __name__ == "__main__":
    main()
