# InfluxDB URL and credentials
INFLUXDB_URL="http://localhost:8086"
INFLUXDB_ADMIN_TOKEN="myadmintoken"  # The initial admin token

# Path to the config.yaml file
CONFIG_FILE="/home/heisenberg/saultrade/creds/config.yaml"

# Fetch the organization ID
ORG_ID=$(curl -s -X GET "${INFLUXDB_URL}/api/v2/orgs" \
  -H "Authorization: Token ${INFLUXDB_ADMIN_TOKEN}" | jq -r '.orgs[0].id')

# Endpoint to create a new token
TOKEN_URL="${INFLUXDB_URL}/api/v2/authorizations"

# Payload for creating a new token
PAYLOAD=$(cat <<EOF
{
  "orgID": "${ORG_ID}",
  "description": "Auto-generated token",
  "permissions": [
    {
      "action": "read",
      "resource": {
        "type": "buckets"
      }
    },
    {
      "action": "write",
      "resource": {
        "type": "buckets"
      }
    }
  ]
}
EOF
)

# Make the request to create a new token
RESPONSE=$(curl -s -X POST "${TOKEN_URL}" \
  -H "Authorization: Token ${INFLUXDB_ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")

# Debug: Print the raw response
echo "Raw Response: ${RESPONSE}"

# Extract the token from the response
NEW_TOKEN=$(echo "${RESPONSE}" | jq -r '.token')

# Debug: Print the extracted token
echo "Extracted Token: ${NEW_TOKEN}"

# Check if the token was successfully generated
if [ -z "${NEW_TOKEN}" ] || [ "${NEW_TOKEN}" == "null" ]; then
  echo "Failed to generate token: ${RESPONSE}"
  exit 1
fi

# Update the config.yaml file with the new token
sed -i "s/token: .*/token: \"${NEW_TOKEN}\"/" "${CONFIG_FILE}"

echo "Successfully updated config.yaml with new token: ${NEW_TOKEN}"