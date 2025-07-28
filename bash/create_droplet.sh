#!/bin/bash

# You can use this bash script to quickly create your droplet. If you are not within a unix system, you can use alternatives
# Postman is an alternative that will work anywhere.
# On windows you can use WSL2 to spin up a linux instance, use cygwin or port to PowerShell if you'd like.

# Set your DigitalOcean API token here
# How to run
# export DO_API_TOKEN="dop_v1_your_actual_token"
# ./create_droplet.sh
API_TOKEN="${DO_API_TOKEN:?DO_API_TOKEN not set}"

# Define the droplet configuration
# Do not change these values!
# We'll be using the smallest vm power there is, just for learning.
# Not following instructions will result in your grade being negativelly impacted!
DROPLET_NAME="example-droplet"
REGION="nyc1"
SIZE="s-1vcpu-512mb-10gb"
IMAGE="ubuntu-24-10-x64"
SSH_FINGERPRINT="d2:20:67:f2:c3:89:f9:40:a3:f4:d7:03:7a:3d:8c:cd"

# Create the droplet using the DigitalOcean API
RESPONSE=$(curl -k -X POST "https://api.digitalocean.com/v2/droplets" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_TOKEN" \
    -d '{"name":"'"$DROPLET_NAME"'","region":"'"$REGION"'","size":"'"$SIZE"'","image":"'"$IMAGE"'","ssh_keys":["'"$SSH_FINGERPRINT"'"]}')

# Extract and print the droplet ID
echo $RESPONSE | jq -r '.droplet'

DROPLET_ID=$(echo $RESPONSE | jq -r '.droplet.id')
echo "Droplet created with ID: $DROPLET_ID"

# Save the droplet ID to a file for later use
echo $DROPLET_ID > droplet_id.txt
