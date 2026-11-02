# Generic build: users bring their own URL + token.
INSTITUTION = None

# Institution build: have your CI overwrite this file, e.g.
# INSTITUTION = {
#     "name": "Example University",
#     "base_url": "https://example.instructure.com",
#     "client_id": "12345",
#     "client_secret": "...",
#     "redirect_port": 53682,
#     "allow_token_login": False,
# }