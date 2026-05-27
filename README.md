# LinkedIn AI Post Automator

Generate and publish one technical LinkedIn post every 2 days at 8:00 PM.

This project uses:

- Google Gemini to generate a software-engineering-focused title and post.
- An online Excel, CSV, or Google Sheet with `title` and `description` columns.
- LinkedIn OAuth 2.0 to get a user access token.
- LinkedIn Posts API to publish to your personal profile.
- Windows Task Scheduler for automation every 2 days.

## 1. LinkedIn App Setup

In your LinkedIn developer app:

1. Add this redirect URL:

   ```text
   http://localhost:8000/callback
   ```

2. Make sure your app has these products/scopes:

   ```text
   openid profile w_member_social
   ```

`w_member_social` is the permission needed to publish posts on behalf of your member profile.

## 2. Install

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and add:

- `GEMINI_API_KEY`
- `LINKEDIN_CLIENT_ID`
- `LINKEDIN_CLIENT_SECRET`
- `CONTENT_SOURCE_URL`

Your online file must have these exact column names in the first row:

```text
title, description
```

Supported sources:

- Public direct `.xlsx` download link
- Public direct `.csv` link
- Google Sheets share URL; the script converts it to CSV export automatically

## 3. Authorize LinkedIn

Run:

```powershell
.\.venv\Scripts\python.exe -u src\main.py login
```

Open the printed URL in your browser and approve access. The command prints `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_PERSON_URN`. Put both values into `.env`.

## 4. Test One Post

Preview without publishing:

```powershell
.\.venv\Scripts\python.exe src\main.py preview
```

Publish immediately:

```powershell
.\.venv\Scripts\python.exe src\main.py post
```

## 5. Schedule Every 2 Days at 8 PM on Windows

Update the paths below if your project lives somewhere else:

```powershell
$Project = "D:\AutomateLinkedInpost"
$Python = "$Project\.venv\Scripts\python.exe"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "src\main.py post" -WorkingDirectory $Project
$Trigger = New-ScheduledTaskTrigger -Daily -DaysInterval 2 -At 8:00PM
Register-ScheduledTask -TaskName "LinkedIn AI Post Every 2 Days" -Action $Action -Trigger $Trigger -Description "Generate and publish a technical LinkedIn post every 2 days"
```

You can check it with:

```powershell
Get-ScheduledTask -TaskName "LinkedIn AI Post Every 2 Days"
```

## 6. Free Hosting on GitHub Actions

This repo includes:

```text
.github/workflows/linkedin-post.yml
```

It runs every day at 2:30 PM UTC, which is 8:00 PM Asia/Kolkata. The script itself checks `POST_INTERVAL_DAYS=2`, so it only posts once every 2 days.

Push the project to a GitHub repository, then add these repository secrets in GitHub:

```text
GEMINI_API_KEY
LINKEDIN_CLIENT_ID
LINKEDIN_CLIENT_SECRET
LINKEDIN_ACCESS_TOKEN
LINKEDIN_PERSON_URN
CONTENT_SOURCE_URL
```

Go to:

```text
GitHub repo -> Settings -> Secrets and variables -> Actions -> New repository secret
```

After secrets are added, go to:

```text
Actions -> LinkedIn Scheduled Post -> Run workflow
```

Use the manual run once to verify it works. After that, GitHub runs it automatically.

## Notes

- Keep `.env` private. It contains your API keys and LinkedIn token.
- The generated post is text-only by default, which is the safest first version.
- Posted rows are tracked in `posts_history.json`, so the same title/description is not posted again.
- LinkedIn tokens can expire. If publishing starts returning authorization errors, repeat the auth step.
