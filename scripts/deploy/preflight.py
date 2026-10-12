import argparse
from common import config, application_session_policy
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["dev", "stage", "uat", "prod"], required=True)
    parser.add_argument("--publishing", action="store_true")
    args = parser.parse_args()
    values = config(args.environment, publishing=args.publishing)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write("session_policy=" + application_session_policy(values, publishing=args.publishing) + "\n")
    print("Application configuration passed for " + values["environment"] + "; no AWS calls made.")
