# Daily Project Startup Guide 🚀

Because this project uses a temporary AI "brain" (Google Colab) and a dynamic tunnel (ngrok), you need to follow these steps every time you restart your PC.

---

## Step 1: Start the AI Brain (Google Colab)
1.  Open [Core_translator.ipynb](src/translator/Core_translator.ipynb) in Google Colab.
2.  **Download Models:** Ensure the first cell (the one we added) is run to download the IndicLID models to `/content/models`.
3.  **ngrok Token:** Ensure your personal ngrok token is pasted in the `ngrok.set_auth_token("...")` line.
4.  **Run All:** Click `Runtime > Run all`.
5.  **Get the URL:** Scroll to the very bottom. Look for the line:
    `✅ Public URL: https://xxxx-xxxx.ngrok-free.app`
    **Copy this URL.**

---

## Step 2: Configure the Backend
1.  Open your local file: `src/backend/chatapp/src/main/resources/application.properties`
2.  Update the `translator.api.url` line with the **new** URL you just copied:
    ```properties
    translator.api.url=https://PASTE_NEW_URL_HERE.ngrok-free.app
    ```
3.  **Database Check:** Ensure your MySQL service is running.

---

## Step 3: Run the Servers
Open two separate terminals:

### Terminal 1: Backend
```powershell
cd src/backend/chatapp
./mvnw spring-boot:run
```
*Wait until you see: `Started ChatappApplication in X seconds`*

### Terminal 2: Frontend
```powershell
cd src/frontend/chat-frontend
npm start
```

---

## Step 4: Login and Verify
1.  Go to `http://localhost:3000`.
2.  If you create a new account and it asks for email verification, manually verify it in MySQL:
    ```sql
    USE chatapp;
    UPDATE users SET verified = true WHERE username = 'your_username';
    ```

---

## Troubleshooting Checklist
- [ ] **Colab says "Out of Space":** Ensure you are downloading models to `/content/models`, NOT to your Google Drive.
- [ ] **Backend fails to start:** Check if MySQL password or `application.properties` keys (Cloudinary/Email) have any typos.
- [ ] **Translation is blank:** Ensure the Colab notebook is still running and hasn't timed out.
