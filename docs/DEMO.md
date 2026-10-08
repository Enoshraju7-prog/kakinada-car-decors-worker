# OBS recording guide

Aim for 3-4 minutes. Record the app window and your microphone. Keep credentials and real supplier bills out of the recording. Use the generated demo at http://127.0.0.1:8003 on Enosh's computer; other computers need their own setup.

## 1. Introduction - 20 seconds

Say:

> Hi, I'm Enosh. I built Kakinada Car Decors to help a shop handle purchases, stock and sales. It also has an AI worker that can read bills, prepare records and check stock. I'll show it using generated data, with approval before posting.

Show Check inventory: the generated item currently has 7 available and 0 incoming.

## 2. Show the completed invoice task - 50 seconds

Open AI assistant and show the saved generated invoice task. Expand its extraction, product lookup and saved-draft steps. Then show the completed approved posting task and its verification result.

Say:

> The model uses functions I defined, such as finding products, preparing drafts and checking saved records. It chooses the next function from the task and what it learns. Azure Document Intelligence reads the bill. The partner reviews the items and sets the selling price. The AI asks for approval before saving the incoming purchase, then checks the saved result.

The earlier task that stopped for clarification is retained. Explain that it saved a draft but did not complete posting; the reviewed posting task is a separate run. Do not present the saved history as a fresh run.

## 3. Run a fresh task while recording - 50 seconds

In AI assistant, with no file attached, enter:

> Check the current generated inventory. Tell me the available and incoming quantities for every saved product, save a shortage report, and read the saved report back. Do not change stock or prices.

Start the task. Show its status, tool steps and final report. The local worker must be running. If it pauses or fails, show the actual result and explain it; do not claim it completed.

Say:

> This is a different task using the same worker. It queries the current inventory, saves a report and reads it back. It isn't just a fixed invoice-extraction pipeline.

## 4. Show stock verification - 30 seconds

Open Check inventory and Activity. Show the saved receipt of 10 and sale of 3, leaving 7.

Say:

> A bill creates incoming stock, not available stock. The partner confirms what physically arrived. In this test I received 10 and sold 3, so 7 remain. The receipt and sale are saved in the stock history. These counts are simulated test inputs, not a real delivery.

## 5. Architecture and limits - 30 seconds

Say:

> React is the interface, FastAPI runs the business logic and PostgreSQL remembers the records. A separate PydanticAI worker calls the application tools. Normal receiving and sales work without the model. I tested duplicate requests, stock limits and approvals, with 56 backend tests passing. Handwriting and vague item names are still difficult, so partners review uncertain details.

Finish on the stock screen or GitHub README. The private live pilot is hosted on DigitalOcean with HTTPS; the recording uses a separate local test database.

## Optional: show duplicate detection

Attach `output/pdf/generated-evaluation-bill.pdf` and use:

> Read this generated bill and check whether it is already recorded. Show the matching purchase and verify its saved details. Do not create another purchase, receive goods or change prices.

This bill is already recorded in the port 8003 workspace. Show the actual result; do not expect a new purchase. For a fresh full invoice-to-receipt recording, use a new generated bill number and review its draft before posting.

## Before sharing

Stop OBS, watch the recording and check that the task result and numbers are readable. Upload the video with viewer access, then test the link in a signed-out browser. Do not show passwords, API keys, private bills or real shop financial records.
