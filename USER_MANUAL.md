# SOTERIA Insurance Surveyor System — User Manual

> **System Name:** SOTERIA Insurance Surveyors & Loss Assessors System  
> **Audience:** Administrative Staff & Licensed Insurance Surveyors  
> **Platform:** Web Portal & Offline-Capable Progressive Web App (PWA)

---

## Table of Contents
1. [System Overview & Role Architecture](#1-system-overview--role-architecture)
2. [Login & Common Navigation](#2-login--common-navigation)
3. [Administrator Portal Guide](#3-administrator-portal-guide)
   - [3.1 Managing Surveyors & Users](#31-managing-surveyors--users)
   - [3.2 Master Data Management](#32-master-data-management)
   - [3.3 Registering a New Claim (Intake Wizard)](#33-registering-a-new-claim-intake-wizard)
   - [3.4 Assigning Claims to Surveyors](#34-assigning-claims-to-surveyors)
   - [3.5 Document Verification & Compliance](#35-document-verification--compliance)
   - [3.6 Claim Approval, Settlement & Closing](#36-claim-approval-settlement--closing)
   - [3.7 Professional Fee Billing & GST Invoicing](#37-professional-fee-billing--gst-invoicing)
4. [Surveyor Portal Guide](#4-surveyor-portal-guide)
   - [4.1 Surveyor Dashboard & Claim Queue](#41-surveyor-dashboard--claim-queue)
   - [4.2 On-Site Inspection & Photo Evidence](#42-on-site-inspection--photo-evidence)
   - [4.3 Documents & LOR (List of Requirements)](#43-documents--lor-list-of-requirements)
   - [4.4 Repair Invoices & Bills](#44-repair-invoices--bills)
   - [4.5 Item-by-Item Loss Assessment](#45-item-by-item-loss-assessment)
   - [4.6 Generating Survey Reports (ILA, ISR, FSR)](#46-generating-survey-reports-ila-isr-fsr)
5. [Field Work & Offline PWA Guide](#5-field-work--offline-pwa-guide)
6. [Frequently Asked Questions & Troubleshooting](#6-frequently-asked-questions--troubleshooting)

---

## 1. System Overview & Role Architecture

The **SOTERIA Insurance Surveyor System** is an end-to-end management platform for licensed insurance surveyors, loss assessors, and survey firm administrators.

The system enforces strict role-based separation:

| Feature / Action | Administrator | Surveyor |
| :--- | :---: | :---: |
| **User & Surveyor Profile Management** | Full Access | No Access |
| **Master Data (Insurers, Insured, Policies)** | Full (Add/Edit) | View Only (via Claim) |
| **Claim Registration** | Full Access | No Access |
| **Surveyor Assignment** | Full Access | View Assigned |
| **Conduct Site Inspection & Upload Photos** | Yes | Yes (Assigned Claims) |
| **Issue LOR (List of Requirements)** | Yes | Yes (Assigned Claims) |
| **Verify Documents / Mark LOR Verified** | Yes (Admin Only) | No (Surveyor can only mark "Received") |
| **Line-Item Financial Assessment** | Full Access | Yes (Assigned Claims) |
| **Draft & Generate Reports (ILA, ISR, FSR)** | Full Access | Yes (Assigned Claims) |
| **Approve & Close Claim** | Yes (Admin Only) | No Access |
| **Professional Fee Invoicing & Billing** | Full Access | View Only / No Edit |
| **Offline PWA Capability** | Yes | Yes (Field Optimized) |

---

## 2. Login & Common Navigation

### 2.1 Logging In
1. Open the portal URL in your web browser:
   - **Production:** `http://<YOUR_SERVER_IP_OR_DOMAIN>/`
   - **Local Development:** `http://127.0.0.1:8000/`
2. Enter your **Username** and **Password**.
3. Click **Sign In**.
   - Admins are automatically routed to the **All Claims & Overview Dashboard**.
   - Surveyors are routed directly to their **My Assigned Claims Dashboard**.

> **Security Note:** Rate throttling is strictly enforced. Five consecutive failed login attempts within 1 minute will temporarily lock login requests for that IP.

### 2.2 Top Navigation & Side Menu
- **Dashboard / Claims:** Overview of ongoing, pending, and completed claims.
- **Master Data (Admins):** Direct links to Insurers, Insured Parties, and Policies.
- **Billing (Admins):** List of professional fee invoices and GST tracking.
- **Offline Indicator (PWA):** A badge in the header displays your connectivity status (`Online` vs `Offline (Outbox Pending)`).
- **User Profile & Logout:** Located at the top right of the navigation bar.

---

## 3. Administrator Portal Guide

### 3.1 Managing Surveyors & Users
Administrators control who can access the system and survey claims:
1. Navigate to **Administration > Users** in the top menu or Django Admin (`/admin/`).
2. To onboard a new surveyor:
   - Create a user account and assign the role **`Surveyor`**.
   - Provide their SLA / License credentials: **Surveyor License Number**, **License Expiry Date**, **Contact Phone**, and **Qualifications**.
3. Only active surveyors with valid licenses appear in claim assignment dropdowns.

---

### 3.2 Master Data Management
Before registering claims, maintain core underwriting records under their respective menu tabs:
- **Insurers (`/insurers/`):** Insurance companies and specific branch offices (e.g., *National Insurance Co. - Mumbai Branch*). Includes GSTIN and contact details.
- **Insured Parties (`/insured/`):** Corporate clients or individuals filing claims (e.g., *Alpha Manufacturing Pvt Ltd*).
- **Policies (`/policies/`):** Insurance policies linked to an insurer, with Sum Insured, Deductible/Excess, Policy Period, and Commodity/Subject Matter.

> **Tip:** You do **not** need to create all master data in advance. While registering a new claim, you can click **`+ Add new Insurer`**, **`+ Add new Insured`**, or **`+ Add new Policy`** directly inside the wizard! A popout window will open and automatically update your dropdown without reloading your form.

---

### 3.3 Registering a New Claim (Intake Wizard)
1. Click **`+ Register New Claim`** from the dashboard.
2. Complete the multi-section wizard:
   - **Section A (Claim Particulars):** Survey Type (Fire, Marine, Engineering, Motor, Property), Priority (Low, Medium, High, Critical), Instruction Date, and Intimation Source.
   - **Section B (Insurer):** Select the underwriting insurance company branch.
   - **Section C (Insured Party):** Select the claimant company.
   - **Section D (Policy):** Select the active policy. The system auto-filters policies belonging to the selected Insurer.
   - **Section E (Loss Particulars):** Date & time of loss, nature of loss, loss location, and initial claimed amount.
   - **Section F (Dynamic LOB Details):** The form dynamically loads line-of-business fields tailored to the selected Survey Type (e.g., fire origin and firefighting measures for *Fire*; consignment invoice and voyage for *Marine*; equipment make/model for *Engineering*).
3. Click **Submit Claim**. The claim is created in status **`CLAIM_INTIMATED`**.

---

### 3.4 Assigning Claims to Surveyors
1. Open the claim from the Claims List.
2. In the right-hand sidebar under **Surveyor Assignment**, select a licensed surveyor from the dropdown.
3. Enter any specific instructions or notes (e.g., *"Urgent visit requested by Insurer due to heavy machinery breakdown"*).
4. Click **Assign Surveyor**.
   - The claim transitions to **`SURVEYOR_ASSIGNED`**.
   - The assigned surveyor immediately receives the claim in their private queue.

---

### 3.5 Document Verification & Compliance
Compliance requires strict two-person control:
- Surveyors or claimants upload documents and acknowledge receipt.
- **Only Admins can verify documents:**
  1. Open the claim and switch to the **Documents** tab.
  2. Review the uploaded file (PDF, JPG, PNG).
  3. Click **Verify Document**.
  4. In the **LOR Requirements** section, click **Mark Verified** on received items.
  - Non-admin attempts to mark verification return a strict `403 Forbidden` response.

---

### 3.6 Claim Approval, Settlement & Closing
Once the Final Survey Report (FSR) is submitted by the surveyor and financial assessments are complete:
1. Open the claim detail page.
2. Verify that:
   - At least one formal report (FSR or ILA) is in **`SUBMITTED`** status.
   - Assessment line items are reviewed.
3. Click the **Approve & Close Claim** button.
4. Provide closing remarks (e.g., *"Approved as per final survey report recommendation. Settled with insurer."*).
5. The claim status moves to **`CLOSED`**. All write actions are safely locked.

---

### 3.7 Professional Fee Billing & GST Invoicing
Administrators generate professional fee service invoices for insurers:
1. Open the claim and click the **Billing** tab (or navigate to `/claims/<id>/billing/create/`).
2. Click **Create Service Invoice**.
3. Enter invoice parameters:
   - **Survey Fee:** Based on scale or agreed loss percentage.
   - **Conveyance / Traveling Expenses:** Site visit traveling charges.
   - **Out of Pocket Expenses:** Photographs, postage, lab testing.
4. **GST Calculation:** The system automatically calculates CGST + SGST (for intra-state) or IGST (for inter-state) based on the Firm GSTIN and Insurer GSTIN.
5. **Manage Line Items:** Add or edit line items while in `DRAFT` status.
6. **Issue Invoice:** Click **Mark Sent** to lock line items against further edits.
7. **Record Payment:** When payment is received from the insurer, click **Record Payment**, choose payment mode (NEFT/RTGS/Cheque), and input transaction ref.
8. **Generate PDF:** Click **Download Invoice PDF** for an IRDAI/GST-compliant printed tax invoice.

---

## 4. Surveyor Portal Guide

### 4.1 Surveyor Dashboard & Claim Queue
When a surveyor logs in, they see their dedicated workspace:
- **My Active Claims:** Only claims assigned to you are visible.
- **Urgent SLA Alerts:** Claims requiring an Immediate Loss Advice (ILA) within 24–48 hours are highlighted.
- **Quick Filters:** Filter by Intimated, Inspection Scheduled, Assessment in Progress, or Reports Submitted.

Click on any claim number to open the multi-tab **Claim Workspace**.

---

### 4.2 On-Site Inspection & Photo Evidence
Switch to the **Inspection** tab:
1. **Schedule / Record Visit:**
   - Inspection Date & Time.
   - Person Contacted on Site & Contact Phone Number.
   - Inspection Location (auto-populated from claim details if blank).
2. **Loss Observations:**
   - Physical Cause of Loss.
   - Extent of Damage & Affected Machinery/Stock.
   - Safety measures & initial salvage mitigation advice.
3. **Capture & Upload Photographs:**
   - Upload multiple site inspection photos simultaneously.
   - The system automatically stamps timestamp metadata and compresses images for fast upload over mobile networks.
4. Click **Save Inspection Details**.
   - If the claim was in `SURVEYOR_ASSIGNED`, saving inspection details automatically transitions the claim to **`INSPECTION_COMPLETED`**.

---

### 4.3 Documents & LOR (List of Requirements)
Under the **Documents / LOR** tab:
1. **Issuing a List of Requirements (LOR):**
   - Click **Add Requirement**.
   - Enter missing document names (e.g., *"Fire Brigade Report"*, *"Repair Estimate from OEM"*, *"Purchase Invoices for raw material"*).
   - Set initial status to **`PENDING`**.
2. **Receiving Documents:**
   - When the insured delivers a document, upload the file under **Upload Document**.
   - Update the requirement status from **`PENDING`** to **`RECEIVED`**.
   - *(Note: Only Administrators can mark an item as `VERIFIED`)*.

---

### 4.4 Repair Invoices & Bills
Under the **Invoices** tab:
1. Click **+ Add Repair Invoice**.
2. Record each commercial invoice or estimate submitted by the insured:
   - Vendor / Contractor Name.
   - Invoice / Estimate Number & Date.
   - Gross Amount claimed.
3. Mark invoice as verified for assessment reference.

---

### 4.5 Item-by-Item Loss Assessment
Under the **Assessment** tab:
1. **Financial Settings:**
   - Set **Salvage Deduction** (estimated scrap value).
   - Set **Depreciation Percentage** (wear & tear deduction).
   - Policy Excess is auto-populated from policy terms.
2. **Add Bill of Quantities (BOQ) Items:**
   - Click **+ Add Assessment Item**.
   - Enter **Item Description** (e.g., *"Rewinding of 50HP Induction Motor"*).
   - Enter **Claimed Amount** vs. **Assessed Quantity & Rate**.
3. **Automated Calculation:**
   - The system instantly recalculates:
     $$\text{Gross Assessed Loss} - \text{Depreciation} - \text{Salvage} - \text{Policy Excess} = \text{Net Assessed Loss}$$
4. Status moves to **`ASSESSMENT_IN_PROGRESS`**.

---

### 4.6 Generating Survey Reports (ILA, ISR, FSR)
Under the **Reports** tab, surveyors generate statutory survey reports:

#### A. Immediate Loss Advice (ILA) — Within 24 to 48 Hours:
- Summarizes initial site visit, extent of damage, estimated gross loss, and budgetary reserve for the insurer.
- Click **Save ILA Draft** & preview the formatted document.
- Transitions claim status to **`ILA_PREPARED`**.

#### B. Interim Survey Report (ISR):
- Progress report submitted while awaiting major contractor estimates or salvage tenders.
- If LOR or financial assessment is not yet completed, you must provide a valid **Reason for skipping LOR/Assessment** before saving.

#### C. Final Survey Report (FSR):
- The definitive statutory loss adjustment report.
- Includes:
  - **Occurrence & Cause Analysis:** Verification against policy warranties and exclusion clauses.
  - **Value at Risk (VAR) & Underinsurance:**
    $$\text{Underinsurance \%} = \max\left(0, \frac{\text{Value at Risk} - \text{Sum Insured}}{\text{Value at Risk}} \times 100\right)$$
  - **Detailed Loss Computation:** Line-item BOQ, salvage recovery, and excess deduction.
  - **Final Recommendation:** Clear opinion on insurer liability and net payable amount.
- Click **Generate FSR PDF** to produce a professional, formatted PDF report complete with company headers, surveyor signature blocks, and attached photo sheets.

---

## 5. Field Work & Offline PWA Guide

The portal includes an integrated **Progressive Web App (PWA)** designed specifically for surveyors working at remote factory sites, ports, or warehouses with poor or zero network connectivity.

### How Offline Mode Operates:
1. **Automatic Detection:** The top bar displays an **Offline** badge as soon as network connection drops.
2. **Offline Data Capture:** You can continue to:
   - Fill out and save Site Inspection notes.
   - Select and queue high-resolution Inspection Photos (stored in local browser storage).
   - Issue LOR items and update requirement statuses.
   - Enter Assessment line items and update report drafts.
3. **Outbox Synchronization:**
   - All offline actions are stored in your device's encrypted **Sync Outbox**.
   - As soon as your device reconnects to Wi-Fi or mobile data, the system automatically replays the outbox in the exact chronological order.
   - Prerequisite actions (such as a new insurer created offline) are automatically reconciled with newly assigned server IDs before dependent claims are uploaded.
4. **Optimistic Concurrency Protection:**
   - If another user modified the same claim while you were offline, the system prevents silent data overwrites by flagging a `409 Conflict` review notice.

---

## 6. Frequently Asked Questions & Troubleshooting

#### Q1: Why can't I edit line items on an assessment or billing invoice?
> **Answer:** If the billing invoice has been moved past `DRAFT` (to `ISSUED` or `PAID`), it is legally locked. Only Administrators can cancel an issued invoice if adjustments are necessary.

#### Q2: Why did my photo upload fail?
> **Answer:** Maximum individual upload size is 50MB. Ensure the image is a standard JPG, PNG, or WEBP format. In offline mode, photos are compressed client-side before queuing.

#### Q3: How do I generate a PDF report on the server?
> **Answer:** The system uses WeasyPrint. Ensure system fonts and rendering packages are installed on the server (`libpango-1.0-0`, `libcairo2`, `fonts-dejavu-core`). If the download hangs, check `tail -f logs/insurance_survey.log`.

#### Q4: Why can't the surveyor mark an LOR requirement as "Verified"?
> **Answer:** By system design, surveyors can set items to `RECEIVED`. The `VERIFIED` state is strictly reserved for Administrators to maintain audit compliance.

---

*Document Version: 2.0 (Production)*  
*Maintained by: SOTERIA IT & Systems Team*
