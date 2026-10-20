# Outlook (university or personal) through Microsoft Graph

udb reads Outlook mail with Microsoft Graph and the device-code login: it shows
a short code, you approve it on any device, and only a token cache is stored.

## 1. Register an app (once)

1. Go to [entra.microsoft.com](https://entra.microsoft.com) with a personal
   Microsoft account (a free account can register apps) → **App registrations** →
   **New registration**.
2. Name: `udb-copilot`. Supported account types: **Accounts in any organizational
   directory and personal Microsoft accounts**.
3. In **Authentication**, turn on **Allow public client flows**.
4. In **API permissions**, add Microsoft Graph delegated permissions `Mail.Read`
   and `User.Read`.
5. Copy the **Application (client) ID**.

## 2. Configure and log in

```yaml
# config/mail.yaml
  - id: udb
    provider: outlook
    address: you@udb.edu.sv
    tenant: organizations      # consumers for @outlook.com / @hotmail.com
    client_id: <application id>
```

```bash
udb mail login udb
```

## If the university blocks it

Many university tenants require an administrator to approve new apps. If the
login says *"Need admin approval"*, you have two options:

- Ask IT to approve the app (it only reads your own mail).
- Forward the university mailbox to your Gmail with an Outlook rule, and let the
  Gmail account cover it.
