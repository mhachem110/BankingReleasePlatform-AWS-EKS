import argparse
from common import config

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=["dev", "stage", "uat", "prod"], required=True)
    parser.add_argument("--publishing", action="store_true")
    args = parser.parse_args()
    values = config(args.environment, publishing=args.publishing)
    print("Application configuration passed for " + values["environment"] + "; no AWS calls made.")
