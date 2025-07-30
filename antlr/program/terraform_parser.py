#!/usr/bin/env python3
import os
import sys
import time
import requests
import argparse
import json
from antlr4 import *
from TerraformSubsetLexer import TerraformSubsetLexer
from TerraformSubsetParser import TerraformSubsetParser
from TerraformSubsetListener import TerraformSubsetListener


class TerraformApplyListener(TerraformSubsetListener):
    def __init__(self):
        self.variables = {}
        self.provider_token_expr = None  # store raw expression (e.g., var.token)
        self.droplet_config = {}

    def enterVariable(self, ctx):
        var_name = ctx.STRING().getText().strip('"')
        for kv in ctx.body().keyValue():
            key = kv.IDENTIFIER().getText()
            if key == "default":
                value = kv.expr().getText().strip('"')
                self.variables[var_name] = value
                print(f"[var] {var_name} = {value}")

    def enterProvider(self, ctx):
        provider_name = ctx.STRING().getText().strip('"')
        if provider_name != "digitalocean":
            raise Exception("Only 'digitalocean' provider is supported.")

        for kv in ctx.body().keyValue():
            key = kv.IDENTIFIER().getText()
            expr = kv.expr().getText()
            if key == "token":
                self.provider_token_expr = expr  # store raw expr for now

    def enterResource(self, ctx):
        type_ = ctx.STRING(0).getText().strip('"')
        name = ctx.STRING(1).getText().strip('"')
        if type_ != "digitalocean_droplet":
            return

        for kv in ctx.body().keyValue():
            key = kv.IDENTIFIER().getText()
            expr_ctx = kv.expr()

            if expr_ctx.list_():
                items = []
                for item in expr_ctx.list_().expr():
                    items.append(item.getText())
                self.droplet_config[key] = items
            else:
                self.droplet_config[key] = expr_ctx.getText().strip('"')

        if "ssh_keys" in self.droplet_config:
            ssh_key_exprs = self.droplet_config["ssh_keys"]

            if isinstance(ssh_key_exprs, list):
                for expr in ssh_key_exprs:
                    if "digitalocean_ssh_key" in expr:
                        self.droplet_config["ssh_key_reference"] = expr
                    elif "file(" in expr:
                        import re, os
                        match = re.search(r'file\("([^"]+)"\)', expr)
                        if match:
                            ssh_path = match.group(1).replace("~", os.path.expanduser("~"))
                            try:
                                with open(ssh_path, "r") as f:
                                    self.droplet_config["ssh_key_content"] = f.read().strip()
                                    self.droplet_config["ssh_key_path"] = ssh_path
                            except FileNotFoundError:
                                raise Exception(f"SSH key file '{ssh_path}' not found")
            else:
                raise Exception(f"Expected ssh_keys to be a list, got: {ssh_key_exprs}")


    def resolve_token(self):
        if not self.provider_token_expr:
            raise Exception("No token specified in provider block.")
        if self.provider_token_expr.startswith("var."):
            var_name = self.provider_token_expr.split(".")[1]
            if var_name in self.variables:
                return self.variables[var_name]
            else:
                raise Exception(
                    f"Undefined variable '{var_name}' used in provider block."
                )
        return self.provider_token_expr.strip('"')


def delete_droplet(api_token: str, droplet_id: str):
    url = f"https://api.digitalocean.com/v2/droplets/{droplet_id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    print("[*] Deleting droplet...")
    response = requests.delete(url, headers=headers)
    response.raise_for_status()
    print(f"[+] Droplet deleted with ID: {droplet_id}")


def create_droplet(api_token, config, ssh_key_path="~/.ssh/id_rsa.pub"):
    url = "https://api.digitalocean.com/v2/droplets"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    with open(os.path.expanduser(ssh_key_path), 'r') as f:
        pub_key = f.read().strip()

    ssh_fingerprint = None
    key_resp = requests.get("https://api.digitalocean.com/v2/account/keys", headers=headers)
    key_resp.raise_for_status()
    keys = key_resp.json()["ssh_keys"]

    for key in keys:
        if key["public_key"] == pub_key:
            ssh_fingerprint = key["fingerprint"]
            print(f"[i] SSH key already exists in DigitalOcean: {key['name']} ({ssh_fingerprint})")
            break

    if not ssh_fingerprint:
        add_resp = requests.post(
            "https://api.digitalocean.com/v2/account/keys",
            headers=headers,
            json={
                "name": f"{config['name']}-key",
                "public_key": pub_key
            },
        )
        add_resp.raise_for_status()
        ssh_info = add_resp.json()["ssh_key"]
        ssh_fingerprint = ssh_info["fingerprint"]
        print(f"[+] SSH key uploaded successfully: {ssh_info['name']} ({ssh_fingerprint})")

    payload = {
        "name": config["name"],
        "region": config["region"],
        "size": config["size"],
        "image": config["image"],
        "ssh_keys": [ssh_fingerprint],
        "backups": False,
        "ipv6": False,
        "user_data": None,
        "private_networking": None,
        "volumes": None,
        "tags": [],
    }

    print("[*] Creating droplet...")
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    droplet = response.json()["droplet"]
    droplet_id = droplet["id"]
    print(f"[+] Droplet created with ID: {droplet_id}")

    print("[*] Waiting for droplet to become active and assigned an IP...")
    while True:
        resp = requests.get(
            f"https://api.digitalocean.com/v2/droplets/{droplet_id}", headers=headers
        )
        droplet_info = resp.json()["droplet"]
        networks = droplet_info["networks"]["v4"]
        public_ips = [n["ip_address"] for n in networks if n["type"] == "public"]
        if public_ips:
            return (public_ips[0], droplet_id)
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(
        prog="Terraform Parser",
        description="Program that makes it easy to define and deploy Terraform configurations",
        epilog="UwU",
    )
    parser.add_argument("filename", help='Filename to "compile".')
    parser.add_argument(
        "-d",
        "--destroy",
        action="store_true",
        help="Whether to destroy the deployment or not.",
    )
    args = parser.parse_args()

    # print("Will use following flags:", args)

    input_stream = FileStream(args.filename)
    lexer = TerraformSubsetLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = TerraformSubsetParser(stream)
    tree = parser.terraform()

    listener = TerraformApplyListener()
    walker = ParseTreeWalker()
    walker.walk(listener, tree)

    token = listener.resolve_token()
    if not listener.droplet_config:
        raise Exception("Missing digitalocean_droplet resource.")

    if args.destroy:
        with open(".tfstate", "r") as file:
            data = json.load(file)
            delete_droplet(token, data["id"])
            print(f"[✓] Resources deleted!")
    else:
        (ip, id) = create_droplet(token, listener.droplet_config)
        with open(".tfstate", "w") as file:
            file.write(f'{{"id": "{id}", "ip": "{ip}"}}')
        print(f"[✓] Droplet available at IP ({ip}) with ID ({id})")


if __name__ == "__main__":
    main()
