#!/bin/bash

# You MUST destroy all droplets.

# Set your DigitalOcean API token here
# export DO_API_TOKEN="dop_v1_your_actual_token"
# ./create_droplet.sh
API_TOKEN="${DO_API_TOKEN:?DO_API_TOKEN not set}"

# Read the droplet ID from the file
DROPLET_ID=$(cat droplet_id.txt)

# Destroy the droplet using the DigitalOcean API
curl -k -X DELETE "https://api.digitalocean.com/v2/droplets/$DROPLET_ID" \
    -H "Authorization: Bearer $API_TOKEN"

echo "Droplet with ID $DROPLET_ID has been destroyed"
