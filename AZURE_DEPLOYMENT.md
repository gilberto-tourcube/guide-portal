# Azure App Service Deployment Guide

This guide explains how to deploy the Guide Portal application to Azure App Service using GitHub Actions.

## Prerequisites

1. **Azure Account** - Active Azure subscription
2. **Azure App Service** - Web App created in Azure Portal
3. **GitHub Repository** - Code pushed to GitHub
4. **Azure CLI** (optional) - For local testing and configuration

## Azure App Service Setup

### 1. Create Azure App Service

1. Go to [Azure Portal](https://portal.azure.com)
2. Click **Create a resource** → **Web App**
3. Configure the following:
   - **Resource Group**: Create new or select existing
   - **Name**: `guide-portal` (or your preferred name)
   - **Publish**: Code
   - **Runtime stack**: Python 3.13
   - **Operating System**: Linux
   - **Region**: Choose closest to your users
   - **Pricing Plan**: Select appropriate tier (B1 or higher recommended)
4. Click **Review + Create** → **Create**

### 2. Configure App Service Settings

After the App Service is created:

1. Go to your App Service in Azure Portal
2. Navigate to **Configuration** → **Application settings**
3. Add the following environment variables (Application settings):

   ```
   SECRET_KEY=<your-secret-key>              # required
   APP_NAME=Tourcube Guide Portal
   DEBUG=False
   COMPANY_CODE=<default-company-code>       # fallback
   MODE=Production                           # fallback
   SSL_VERIFY=true
   ALLOWED_ORIGINS=[]                        # JSON list, e.g., ["https://portal.example.com"]
   ```

4. Navigate to **Configuration** → **General settings**
5. Set **Startup Command**: `bash startup.sh`
6. Click **Save**

### 3. Get Publish Profile

1. In your App Service, click **Get publish profile** (top menu)
2. Download the `.PublishSettings` file
3. Open the file and copy its entire contents (XML)
4. You'll need this for GitHub Secrets

## GitHub Actions Setup

### 1. Configure GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:
   - **Name**: `AZURE_WEBAPP_PUBLISH_PROFILE` (or the name referenced in the workflow)  
     **Value**: full publish profile (.PublishSettings/.xml)
   - **Name**: `APIKEY_JSON`  
     **Value**: full contents of `config/apikey.json` (including `TestDomains` and `ProductionDomains`)
5. Click **Add secret**

### 2. Update Workflow Configuration

Workflow used: `.github/workflows/main_guideportal.yml`
- `publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}` — confirm the secret name.
- Step “Restore apikey.json from secret” writes `config/apikey.json` from `APIKEY_JSON`.
- Python set to 3.13.

### 3. Customize Deployment Branches

The workflow runs on pushes to `main` (default). To change:

```yaml
on:
  push:
    branches:
      - main        # Deploy on push to main
      - production  # Deploy on push to production
```

## Deployment Process

### Automatic Deployment

1. Make changes to your code
2. Commit and push to `main` or `production` branch:
   ```bash
   git add .
   git commit -m "Your commit message"
   git push origin main
   ```
3. GitHub Actions will automatically:
   - Build the application
   - Run tests (if configured)
   - Deploy to Azure App Service
4. Monitor deployment progress in **Actions** tab on GitHub

### Manual Deployment

You can also trigger deployment manually:

1. Go to your GitHub repository
2. Click **Actions** tab
3. Select **Deploy to Azure App Service** workflow
4. Click **Run workflow** → **Run workflow**

## Monitoring and Troubleshooting

### View Logs in Azure

1. Go to Azure Portal → Your App Service
2. Navigate to **Monitoring** → **Log stream**
3. View real-time application logs

### Check Deployment Status

1. GitHub: Check **Actions** tab for workflow status
2. Azure Portal: Go to **Deployment Center** to see deployment history

### Common Issues

#### Issue: App not starting
- **Solution**: Check startup command in App Service Configuration
- Verify: `bash startup.sh` is set as startup command

#### Issue: Dependencies not installing
- **Solution**: Ensure `requirements.txt` is in root directory
- Check: Build logs in GitHub Actions for errors

#### Issue: Static files not loading
- **Solution**: Verify static files are in `static/` directory
- Check: App Service has access to static directory

#### Issue: Environment variables not working
- **Solution**: Double-check Application Settings in Azure Portal
- Ensure: All required environment variables are set

### Health Check

Visit your app's health endpoint:
```
https://your-app-name.azurewebsites.net/health
```

Expected response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

## File Structure

The deployment uses these files:

```
guide-portal/
├── .github/
│   └── workflows/
│       └── main_guideportal.yml  # GitHub Actions workflow
├── .deployment                    # Azure deployment config
├── startup.sh                     # Azure startup script
├── requirements.txt               # Python dependencies
├── app/
│   └── main.py                    # FastAPI application
└── static/                        # Static files
```

## Security Best Practices

1. **Never commit secrets** to the repository
2. **Use environment variables** for all sensitive data
3. **Enable HTTPS only** in Azure App Service
4. **Set up custom domain** with SSL certificate
5. **Enable Application Insights** for monitoring
6. **Configure CORS** properly in production
7. **Set up authentication** for admin routes

## Scaling

### Vertical Scaling (Scale Up)
1. Go to App Service → **Scale up (App Service plan)**
2. Select a higher tier for more CPU/RAM

### Horizontal Scaling (Scale Out)
1. Go to App Service → **Scale out (App Service plan)**
2. Configure auto-scaling rules based on:
   - CPU percentage
   - Memory percentage
   - HTTP queue length

## Backup and Recovery

### Configure Backups
1. Go to App Service → **Backups**
2. Configure automatic backups
3. Set backup schedule and retention

### Restore from Backup
1. Go to **Backups** → Select backup
2. Click **Restore** → Choose restore options

## Production Checklist

Before going to production:

- [ ] Set `DEBUG=False` in environment variables
- [ ] Configure proper CORS settings
- [ ] Set strong `SECRET_KEY`
- [ ] Configure custom domain and SSL
- [ ] Set up Application Insights
- [ ] Configure proper logging
- [ ] Set up database backups (if using database)
- [ ] Configure auto-scaling rules
- [ ] Set up health check alerts
- [ ] Test all authentication flows
- [ ] Verify all API integrations
- [ ] Load test the application
- [ ] Document all environment variables

## Support

For issues or questions:
1. Check Azure App Service logs
2. Review GitHub Actions workflow logs
3. Contact Azure Support
4. Review FastAPI documentation

## Additional Resources

- [Azure App Service Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [FastAPI Deployment Guide](https://fastapi.tiangolo.com/deployment/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
