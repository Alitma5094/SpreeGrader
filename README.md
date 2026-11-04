
# SpreeGrader

SpreeGrader is a desktop app for quickly grading Canvas submissions with file types the web interface does not support (like AutoCad and Vectorworks).


## Installation

Clone the git repository and install the dependencies

```bash
  git clone https://github.com/Alitma5094/SpreeGrader.git
  cd spreegrader
  uv sync
```

## Configuration
SpreeGrader can be compiled with two different versions depending on the desired authentication method. The standard Briefcase build supports Personal Access Tokens, which are recommended for individual users.

Many institutions restrict the creation of Personal Access Tokens by individuals. In that case, contact your Canvas administrator to obtain the proper [Developer Keys](https://community.instructure.com/en/kb/articles/661518-how-do-i-manage-developer-keys-for-an-account).

To use Spreegrader with any institution by manually configuring a domain and [Personal Access Token](https://community.instructure.com/en/kb/articles/662901-how-do-i-manage-api-access-tokens-in-my-user-account), use the command:
```bash
briefcase build
```

To preconfigure the build with your institution's OAuth credentials, follow the instructions in the separate build script:
```bash
python build_institution.py
```
    
## License

This project is licensed under the BSD 3-Clause license. 

This project is not associated with Instructure. All trademarks are property of their respective owners.

