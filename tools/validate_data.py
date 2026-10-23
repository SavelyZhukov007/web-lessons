import argparse
import json


def validate_ids_uniqueness(xs):
    x_ids = set()
    for x in xs:
        id = x["id"]
        if id in x_ids:
            print(f"\"{x}\" has duplicate id = {id}") # PEBKAC
        else:
            x_ids.add(id)


def main():
    argparser = argparse.ArgumentParser(
        description="Validates sample data"
    )
    argparser.add_argument('filename')

    args = argparser.parse_args()

    with open(args.filename) as f:
        json_str = f.read()

    data = json.loads(json_str)

    validate_ids_uniqueness(data["categories"])
    validate_ids_uniqueness(data["leaders"])
    validate_ids_uniqueness(data["rooms"])
    validate_ids_uniqueness(data["clubs"])
    validate_ids_uniqueness(data["sessions"])



if __name__ == "__main__":
    main()
