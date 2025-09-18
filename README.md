# Discord Webhook Results Monitor Bot

## 🎯 Purpose
This bot monitors exam result websites and sends instant notifications to Discord when results are published. Perfect for staying updated without constantly checking websites manually.

## ✨ Features
- **Real-time monitoring** - Checks every second for result updates
- **Rich Discord notifications** - Beautiful embeds with all result details  
- **Batch processing** - Handles multiple registration numbers efficiently
- **File attachments** - Sends actual result HTML files to Discord
- **Error handling** - Robust retry logic and error notifications
- **GitHub Actions deployment** - Runs completely free in the cloud

## 🚀 Quick Setup

### 1. Discord Setup (2 minutes)
1. Create a Discord server and channel for results
2. Go to Server Settings → Integrations → Create Webhook
3. Copy the webhook URL (save it securely!)

### 2. GitHub Repository Setup
1. Fork/clone this repository
2. Add your registration numbers to `registration_numbers.txt` (one per line)
3. Go to repository Settings → Secrets and variables → Actions
4. Add a new repository secret:
   - **Name:** `DISCORD_WEBHOOK`
   - **Value:** Your Discord webhook URL

### 3. Deploy & Run
1. Go to Actions tab in your repository
2. Click "Run workflow" to start monitoring manually
3. Or wait for the scheduled runs (every 5 minutes)

## 📝 Configuration

### Registration Numbers Format
Edit `registration_numbers.txt`:
```
12345678901
12345678902
12345678903
```

### Environment Variables
- `DISCORD_WEBHOOK`: Your Discord webhook URL (required)

## 📊 What You'll Get

### Real-time Notifications
- ✅ **Result Found** - Rich embed with details + HTML file attachment
- 🔍 **Monitoring Status** - Regular updates on bot status
- ⚠️ **Error Alerts** - Notifications if website is down
- 📊 **Final Summary** - Complete statistics when processing finishes

### Rich Discord Messages
- Beautiful colored embeds
- File attachments with actual results
- Progress tracking
- Error reporting
- Success statistics

## 🛠️ Technical Details

### Monitoring Strategy
- Checks target website every second
- Detects when results go live automatically
- Processes all registration numbers in parallel batches
- Handles website overload gracefully

### GitHub Actions Features
- Scheduled runs every 5 minutes
- Manual trigger available
- No external hosting required
- Completely free operation

### Error Handling
- Automatic retries for failed requests
- Website overload detection
- Rate limiting protection
- Comprehensive logging

## 🔧 Customization

### Change Check Interval
Edit `CHECK_INTERVAL = 1` in `discord_bot.py` (seconds)

### Modify Batch Size
Edit `BATCH_SIZE = 20` in `discord_bot.py`

### Update Target Website
Change `URL` and `RESULT_URL_TEMPLATE` variables

## 📱 Discord Setup Guide

### Creating Webhook (Detailed)
1. **Open Discord** → Go to your server
2. **Right-click server name** → "Server Settings"  
3. **Click "Integrations"** → "Webhooks"
4. **Click "Create Webhook"**
5. **Configure:**
   - Name: "Result Monitor Bot"
   - Channel: Select your results channel
6. **Copy Webhook URL** (looks like: `https://discord.com/api/webhooks/...`)

### Security Note
Keep your webhook URL private! Anyone with this URL can send messages to your Discord channel.

## 🎉 Benefits Over Other Solutions

### vs Telegram Bots
- ✅ No bot token management
- ✅ Better file handling  
- ✅ Rich formatting options
- ✅ No rate limiting issues
- ✅ Works perfectly with GitHub Actions

### vs Email Notifications
- ✅ Instant delivery
- ✅ Rich formatting
- ✅ File attachments
- ✅ Mobile notifications
- ✅ No email provider setup

### vs Manual Checking
- ✅ 24/7 automated monitoring
- ✅ Instant notifications
- ✅ Never miss results
- ✅ Handles multiple numbers
- ✅ Complete automation

## 🆘 Troubleshooting

### Bot Not Responding
1. Check webhook URL is correct in repository secrets
2. Verify Discord webhook still exists
3. Check Actions logs for error messages

### Missing Notifications
1. Ensure webhook URL has proper permissions
2. Check Discord channel permissions
3. Verify registration numbers format

### File Upload Issues
1. Check HTML file size (Discord limit: 8MB)
2. Verify webhook has attachment permissions

## 📞 Support
- Check GitHub Actions logs for detailed error information
- Verify all setup steps were followed correctly
- Test webhook URL manually using online tools

---

**Happy result hunting! 🎯** This bot will make sure you're the first to know when your results are published!