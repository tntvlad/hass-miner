# HAR Files for API Analysis

Place Chrome/browser HAR (HTTP Archive) files here to analyze miner APIs.

## How to capture HAR files:

1. Open Chrome DevTools (F12)
2. Go to the **Network** tab
3. Navigate to your miner's web interface and perform actions
4. Right-click in the Network panel → **Save all as HAR with content**
5. Save the `.har` file in this folder

## Notes

- These files may contain sensitive data (passwords, IPs, tokens)
- This folder is gitignored - files here won't be committed
- Use these to reverse-engineer VNish/BOS API endpoints
