# Azure student deployment

Student verification and subscription activation completed on 16 November 2026.
See [the current deployment guide](../CLOUD_SETUP.md) and `status.json` for operational status.

Subscription: Azure for Students. Spending limit: On. No paid upgrade authorized.
Resources: one Standard_B1s Ubuntu VM in India South Central, persistent 32 GB
Standard_LRS OS disk, static public IP, restricted SSH, and public HTTPS gateway.
Student allowances/credit are finite; disk and network charges may consume credit.

Use Safari for account interactions. The Azure CLI session cache and SSH private
key are kept outside the source archive. Access keys are private local files and
only SHA256 hashes are configured on the server.

Microsoft references verified 16 November 2026:
- https://azure.microsoft.com/en-us/free/students/
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit
- https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/azurestudents-subscription-disabled
