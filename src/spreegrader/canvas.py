import requests
from urllib.parse import urljoin


class CanvasError(RuntimeError):
    def __init__(self, status_code, url):
        super().__init__(f"HTTP {status_code} from {url}")
        self.status_code = status_code


class Canvas:
    def __init__(self, base_url: str, auth):
        self.base_url = base_url.rstrip("/")
        self.auth = auth

    def _request(self, method, url, **kwargs):
        request_url = urljoin(f"{self.base_url}/", url)
        for attempt in (0, 1):
            self.auth.ensure_fresh()
            headers = {**self.auth.headers(), "User-Agent": "Spreegrader/0.1"}
            response = requests.request(method, request_url, headers=headers, **kwargs)
            if response.status_code == 401 and attempt == 0 and self.auth.refresh():
                response.close()
                continue
            break
        if not response.ok:
            raise CanvasError(response.status_code, request_url)
        return response


    def _get_all(self, path, params=None):
        url = f"{self.base_url}/api/v1{path}"
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results = []
        while url:
            r = self._request("GET", url, params=params)
            data = r.json()
            results.extend(data if isinstance(data, list) else [data])
            url = r.links.get("next", {}).get("url")
            params = None
        return results

    def get_courses(self):
        return self._get_all("/courses")

    def get_current_user(self):
        return self._request("GET", "/api/v1/users/self").json()

    def get_assignments(self, course_id):
        return self._get_all(f"/courses/{course_id}/assignments")

    def get_submissions(self, course_id, assignment_id):
        return self._get_all(
            f"/courses/{course_id}/assignments/{assignment_id}/submissions",
            {"include[]": ["user", "submission_comments"]},
        )

    def update_submission(self, course_id, assignment_id, user_id, data):
        url = (
            f"{self.base_url}/api/v1/courses/{course_id}"
            f"/assignments/{assignment_id}/submissions/{user_id}"
        )
        return self._request("PUT", url, data=data).json()

    def download_file(self, url, dest):
        r = self._request("GET", url, stream=True, timeout=120)
        with r:
            with open(dest, "wb") as f:
                f.writelines(r.iter_content(chunk_size=1 << 16))
