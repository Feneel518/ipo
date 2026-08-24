# IPO RHP Extraction with Gemini API
## Low-cost, production-oriented implementation guide

**Recommended primary model:** `gemini-2.5-flash-lite`  
**Recommended stack:** Node.js / TypeScript + `@google/genai` + PostgreSQL + Cloudflare R2/S3 + Railway  
**Use case:** Automatically process roughly 2–5 IPO RHP PDFs per day and store structured, auditable IPO data.

> This design deliberately does **not** use RAG, embeddings, a vector database, fine-tuning, or a self-hosted LLM. At this volume, direct PDF processing is simpler and very inexpensive.

---

# 1. What we are building

The target flow is:

```text
NSE / BSE / IPO source
        |
        v
Download RHP PDF
        |
        +----------------------+
        |                      |
        v                      v
Cloudflare R2 / S3        Gemini Files API
(original permanent copy)      |
                               v
                    gemini-2.5-flash-lite
                               |
                               v
                      Strict structured JSON
                               |
                  +------------+-------------+
                  |                          |
                  v                          v
             Validation              Verification rules
                  |                          |
                  +------------+-------------+
                               |
                               v
                    Deterministic calculations
                               |
                               v
                           PostgreSQL
                               |
                               v
                       IPO Dekho API / UI
```

The core principle is:

> **The LLM extracts facts. Your backend calculates metrics.**

Do not ask the LLM to calculate values that your application can calculate deterministically.

Examples:

- LLM extracts FY2024 revenue.
- LLM extracts FY2025 revenue.
- LLM extracts FY2026 revenue.
- Backend calculates sales CAGR.
- Backend calculates margins.
- Backend calculates debt/equity.
- Backend calculates interest coverage where the required inputs are available.
- Backend calculates receivable days where the required inputs are available.

This gives you much better reliability.

---

# 2. Why Gemini 2.5 Flash-Lite

Use:

```text
gemini-2.5-flash-lite
```

as the default extraction model.

It is suitable for this workload because it provides:

- native PDF/document understanding;
- a large context window;
- structured JSON output;
- very low input cost;
- low output cost;
- good throughput for extraction jobs.

Keep a more capable fallback model available:

```text
gemini-2.5-flash
```

Use the fallback only when:

- important numbers are missing;
- conflicting values are found;
- the PDF has difficult tables;
- the first model reports low confidence;
- your validation rules fail.

This keeps average cost low.

---

# 3. Important architecture rule: one permanent copy, one temporary AI copy

Your RHP should exist permanently in your own object storage.

For example:

```text
Cloudflare R2
└── rhp/
    └── 2026/
        └── company-name/
            └── rhp.pdf
```

The Gemini Files API copy should be treated as temporary processing storage.

Store these fields in your database:

```text
rhpStorageKey
rhpSha256
rhpOriginalUrl
geminiFileName
geminiFileUri
geminiFileExpiresAt
```

Do **not** depend on Gemini Files API as your permanent RHP storage.

---

# 4. Create a Gemini API key

Go to Google AI Studio and create a Gemini API key.

Store the key only on the backend.

Never put it inside:

```text
NEXT_PUBLIC_*
```

and never expose it to your mobile/web application.

Create an environment variable:

```env
GEMINI_API_KEY=your_secret_key
```

On Railway, add it under your service's environment variables.

---

# 5. Install the current Google GenAI SDK

Use the newer GA package:

```bash
npm install @google/genai
```

Do **not** start a new project with the older package:

```text
@google/generative-ai
```

For validation and utility code:

```bash
npm install zod
```

If you are using Prisma:

```bash
npm install @prisma/client
npm install -D prisma
```

A useful minimal dependency set is therefore:

```bash
npm install @google/genai zod
```

---

# 6. Suggested project structure

```text
src/
├── lib/
│   ├── gemini.ts
│   ├── storage.ts
│   ├── db.ts
│   └── logger.ts
│
├── ipo/
│   ├── schema/
│   │   ├── ipo-extraction.schema.ts
│   │   └── ipo-extraction.zod.ts
│   │
│   ├── prompts/
│   │   └── rhp-extraction.prompt.ts
│   │
│   ├── services/
│   │   ├── download-rhp.ts
│   │   ├── upload-to-gemini.ts
│   │   ├── extract-rhp.ts
│   │   ├── validate-extraction.ts
│   │   ├── verify-extraction.ts
│   │   ├── calculate-financials.ts
│   │   └── process-rhp.ts
│   │
│   └── types.ts
│
├── workers/
│   └── ipo-rhp.worker.ts
│
└── scripts/
    └── test-rhp.ts
```

You do not need to match this exactly, but separating extraction, validation, calculation, and persistence is important.

---

# 7. Initialize the Gemini client

Create:

```text
src/lib/gemini.ts
```

```ts
import { GoogleGenAI } from "@google/genai";

if (!process.env.GEMINI_API_KEY) {
  throw new Error("GEMINI_API_KEY is not configured");
}

export const gemini = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY,
});
```

Only initialize this on the server.

---

# 8. Download an RHP

Your ingestion system should first download the PDF itself.

Example:

```ts
import { createHash } from "node:crypto";
import { writeFile } from "node:fs/promises";

export async function downloadRhp(url: string, outputPath: string) {
  const response = await fetch(url, {
    redirect: "follow",
    headers: {
      "User-Agent": "IPO-Dekho/1.0",
    },
  });

  if (!response.ok) {
    throw new Error(
      `RHP download failed: ${response.status} ${response.statusText}`
    );
  }

  const contentType = response.headers.get("content-type") ?? "";

  const buffer = Buffer.from(await response.arrayBuffer());

  if (buffer.length < 10_000) {
    throw new Error("Downloaded RHP is unexpectedly small");
  }

  // Do not depend only on Content-Type because some exchange/CDN
  // endpoints return PDFs with generic content types.
  const pdfHeader = buffer.subarray(0, 5).toString("ascii");

  if (pdfHeader !== "%PDF-") {
    throw new Error("Downloaded file does not look like a PDF");
  }

  await writeFile(outputPath, buffer);

  const sha256 = createHash("sha256")
    .update(buffer)
    .digest("hex");

  return {
    bytes: buffer.length,
    sha256,
    contentType,
  };
}
```

The SHA-256 hash is important.

It lets you avoid processing the same RHP twice.

Before creating a processing job, query:

```text
WHERE rhpSha256 = ?
```

If that document has already been processed successfully, reuse the result.

---

# 9. Store the RHP permanently

Store the original PDF in:

- Cloudflare R2;
- Amazon S3;
- Backblaze B2;
- another S3-compatible object store.

For your volume, Cloudflare R2 is a reasonable option.

Example object key:

```text
rhp/2026/08/company-slug/<sha256>.pdf
```

Store metadata in PostgreSQL:

```json
{
  "originalUrl": "...",
  "storageKey": "rhp/2026/08/company/abc123.pdf",
  "sha256": "abc123...",
  "fileSize": 48302012
}
```

---

# 10. Upload the RHP to Gemini Files API

For large RHPs, use the Files API rather than embedding the entire PDF as base64 in every request.

Example:

```ts
import { gemini } from "@/lib/gemini";

export async function uploadRhpToGemini(filePath: string) {
  const uploaded = await gemini.files.upload({
    file: filePath,
    config: {
      mimeType: "application/pdf",
      displayName: filePath.split("/").pop() ?? "ipo-rhp.pdf",
    },
  });

  if (!uploaded.name || !uploaded.uri) {
    throw new Error("Gemini file upload returned no file name/URI");
  }

  return uploaded;
}
```

---

# 11. Wait until Gemini finishes processing the PDF

A large uploaded document can enter a processing state.

Create a helper:

```ts
import { gemini } from "@/lib/gemini";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForGeminiFile(
  fileName: string,
  timeoutMs = 5 * 60 * 1000
) {
  const startedAt = Date.now();

  while (true) {
    const file = await gemini.files.get({
      name: fileName,
    });

    if (file.state === "ACTIVE") {
      return file;
    }

    if (file.state === "FAILED") {
      throw new Error(`Gemini failed to process file ${fileName}`);
    }

    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`Timed out waiting for Gemini file ${fileName}`);
    }

    await sleep(2000);
  }
}
```

Do not poll every 100 ms.

A 2–5 second interval is enough for this type of background task.

---

# 12. The most important design choice: evidence-first fields

Do not use this:

```json
{
  "revenue": 729.53
}
```

Use this:

```json
{
  "revenue": {
    "value": 729.53,
    "unit": "INR_CRORE",
    "sourcePages": [287],
    "confidence": 0.99,
    "evidence": "Revenue from operations..."
  }
}
```

Every important fact should ideally contain:

```text
value
unit
sourcePages
confidence
evidence
status
```

`status` can be:

```text
FOUND
NOT_FOUND
AMBIGUOUS
CONFLICTING
NOT_APPLICABLE
```

This makes your product auditable.

---

# 13. Do not let the AI invent missing data

The prompt must explicitly say:

```text
If the value is not present in the RHP, return null.

Do not estimate.

Do not infer a current market value.

Do not use outside knowledge.

Do not fabricate a page number.

If two values conflict, mark the field CONFLICTING.
```

This is extremely important for financial documents.

---

# 14. Recommended base evidence schema

A reusable numerical evidence object could look like this:

```ts
const numericEvidenceSchema = {
  type: "object",
  properties: {
    value: {
      type: ["number", "null"],
    },
    unit: {
      type: ["string", "null"],
    },
    sourcePages: {
      type: "array",
      items: { type: "integer" },
    },
    confidence: {
      type: "number",
      minimum: 0,
      maximum: 1,
    },
    evidence: {
      type: ["string", "null"],
    },
    status: {
      type: "string",
      enum: [
        "FOUND",
        "NOT_FOUND",
        "AMBIGUOUS",
        "CONFLICTING",
        "NOT_APPLICABLE",
      ],
    },
  },
  required: [
    "value",
    "unit",
    "sourcePages",
    "confidence",
    "evidence",
    "status",
  ],
};
```

Keep evidence snippets short.

You do not need to store entire paragraphs from the RHP.

---

# 15. Recommended extraction schema

For IPO Dekho, divide the output into logical sections.

```json
{
  "document": {},
  "company": {},
  "business": {},
  "industry": {},
  "ipo": {},
  "financials": {},
  "balanceSheet": {},
  "cashFlow": {},
  "ratiosReported": {},
  "promoters": {},
  "customers": {},
  "suppliers": {},
  "operations": {},
  "capacity": {},
  "objectsOfIssue": {},
  "peerComparison": {},
  "litigation": {},
  "risks": {},
  "strengths": {},
  "governmentBenefits": {},
  "extractionMeta": {}
}
```

Do not start with hundreds of fields on day one.

Start with the fields your UI actually needs.

---

# 16. IPO fields I recommend extracting

## Company

```text
companyName
legalName
cin
incorporationDate
registeredOffice
corporateOffice
website
industry
subIndustry
businessDescription
```

## What the company sells

```text
products
services
brands
revenueSegments
geographies
```

## Competitive positioning

```text
competitiveStrengths
whyCustomersChooseCompany
entryBarriers
certifications
manufacturingCapabilities
distributionNetwork
```

## Growth

```text
growthDrivers
expansionPlans
capacityExpansion
newProducts
newGeographies
orderBook
industryTailwinds
```

## IPO

```text
issueType
freshIssueAmount
ofsAmount
totalIssueAmount
priceBandLow
priceBandHigh
lotSize
faceValue
preIssueShares
postIssueShares
objectsOfIssue
sellingShareholders
```

Some IPO timing/allotment fields may be better sourced from NSE/BSE or your IPO data provider rather than the RHP.

---

# 17. Financial fields to extract

At minimum, extract 3 years where available.

Example:

```json
{
  "financials": [
    {
      "financialYear": "FY2024",
      "revenueFromOperations": {},
      "totalIncome": {},
      "ebitda": {},
      "profitBeforeTax": {},
      "profitAfterTax": {},
      "financeCosts": {},
      "depreciation": {},
      "operatingCashFlow": {},
      "investingCashFlow": {},
      "financingCashFlow": {},
      "tradeReceivables": {},
      "inventory": {},
      "totalAssets": {},
      "totalBorrowings": {},
      "totalEquity": {},
      "netWorth": {}
    }
  ]
}
```

Where possible, prefer explicitly reported financial statement values.

For EBITDA, be careful:

- some RHPs report EBITDA;
- some define "Adjusted EBITDA";
- some only provide enough information for you to calculate a proxy.

Do not mix these silently.

Store a field such as:

```text
metricBasis = REPORTED | CALCULATED
```

---

# 18. Extract reported ratios separately

RHPs sometimes contain KPI/ratio tables.

Extract reported values such as:

```text
ROE
ROCE
EBITDA margin
PAT margin
Debt/Equity
EPS
NAV
RONW
```

But store them under something like:

```text
reportedRatios
```

Then maintain separately:

```text
calculatedRatios
```

This lets you compare:

```text
reported ROCE: 18.7%
calculated ROCE: 18.3%
```

A meaningful difference can trigger review.

---

# 19. Customer concentration

Extract:

```text
topCustomerRevenuePct
top5CustomersRevenuePct
top10CustomersRevenuePct
customerNamesIfDisclosed
customerIndustries
customerConcentrationRisk
```

Important:

Many RHPs intentionally do not name all customers.

Do not force Gemini to guess customer names.

---

# 20. Promoter data

Extract:

```text
promoterNames
promoterGroup
preIssuePromoterHolding
postIssuePromoterHolding
pledgedShares
promoterRemuneration
relatedPartyTransactions
```

Some pledge information may not be stated in the way you expect.

Use `NOT_FOUND` rather than interpreting absence as zero.

These are different:

```text
pledgedSharesPct = 0
```

and:

```text
pledgedSharesPct = null
status = NOT_FOUND
```

Never conflate the two.

---

# 21. Peer comparison data

The RHP can usually provide the peer comparison table included by the issuer.

Extract:

```text
peerName
revenue
PAT
EPS
NAV
RONW
PE
marketPrice
financialPeriod
sourcePage
```

But do not treat RHP peer P/E as the current market P/E after the RHP date.

For current valuation, fetch fresh market data separately.

---

# 22. Government benefits

This needs careful handling.

Extract only benefits actually supported by the RHP, for example:

```text
PLI scheme
government subsidy
tax incentive
industrial policy benefit
export incentive
sector-specific government spending
regulatory mandate
government customer exposure
```

Each item should include:

```json
{
  "scheme": "string or null",
  "description": "string",
  "benefitType": "DIRECT | INDIRECT | INDUSTRY_TAILWIND",
  "sourcePages": [123],
  "confidence": 0.92
}
```

Do not ask the model to use current government policy knowledge in the same RHP extraction pass.

Current policy analysis should be a separate web/data task.

---

# 23. Risk extraction

Do not dump all 80–150 RHP risk factors into your primary IPO table.

Instead extract:

```text
criticalRisks
customerConcentrationRisks
supplierRisks
regulatoryRisks
litigationRisks
workingCapitalRisks
promoterRisks
relatedPartyRisks
geographicRisks
capacityUtilizationRisks
debtRisks
```

Recommended output:

```json
{
  "title": "Dependence on top customers",
  "severity": "HIGH",
  "description": "A material percentage of revenue is derived from...",
  "sourcePages": [42, 43],
  "confidence": 0.97
}
```

Severity is an AI classification, not an RHP fact.

Mark it accordingly in your data model.

---

# 24. A practical JSON Schema

You can begin with a smaller schema like this and expand it over time.

```ts
export const ipoExtractionJsonSchema = {
  type: "object",

  properties: {
    company: {
      type: "object",
      properties: {
        name: {
          type: ["string", "null"],
        },
        industry: {
          type: ["string", "null"],
        },
        description: {
          type: ["string", "null"],
        },
        productsServices: {
          type: "array",
          items: {
            type: "string",
          },
        },
      },
      required: [
        "name",
        "industry",
        "description",
        "productsServices",
      ],
    },

    business: {
      type: "object",
      properties: {
        competitiveStrengths: {
          type: "array",
          items: {
            type: "object",
            properties: {
              value: { type: "string" },
              sourcePages: {
                type: "array",
                items: { type: "integer" },
              },
              confidence: { type: "number" },
            },
            required: ["value", "sourcePages", "confidence"],
          },
        },

        growthDrivers: {
          type: "array",
          items: {
            type: "object",
            properties: {
              value: { type: "string" },
              sourcePages: {
                type: "array",
                items: { type: "integer" },
              },
              confidence: { type: "number" },
            },
            required: ["value", "sourcePages", "confidence"],
          },
        },
      },
      required: ["competitiveStrengths", "growthDrivers"],
    },

    financials: {
      type: "array",
      items: {
        type: "object",

        properties: {
          financialYear: {
            type: "string",
          },

          revenueFromOperations: numericEvidenceSchema,
          profitAfterTax: numericEvidenceSchema,
          financeCosts: numericEvidenceSchema,
          operatingCashFlow: numericEvidenceSchema,
          tradeReceivables: numericEvidenceSchema,
          totalBorrowings: numericEvidenceSchema,
          totalEquity: numericEvidenceSchema,
        },

        required: [
          "financialYear",
          "revenueFromOperations",
          "profitAfterTax",
          "financeCosts",
          "operatingCashFlow",
          "tradeReceivables",
          "totalBorrowings",
          "totalEquity",
        ],
      },
    },

    promoters: {
      type: "object",

      properties: {
        names: {
          type: "array",
          items: { type: "string" },
        },

        preIssueHoldingPct: numericEvidenceSchema,
        postIssueHoldingPct: numericEvidenceSchema,
        pledgedSharesPct: numericEvidenceSchema,
      },

      required: [
        "names",
        "preIssueHoldingPct",
        "postIssueHoldingPct",
        "pledgedSharesPct",
      ],
    },

    risks: {
      type: "array",

      items: {
        type: "object",

        properties: {
          title: { type: "string" },

          category: {
            type: "string",
            enum: [
              "CUSTOMER",
              "SUPPLIER",
              "DEBT",
              "WORKING_CAPITAL",
              "REGULATORY",
              "LITIGATION",
              "PROMOTER",
              "RELATED_PARTY",
              "OPERATIONS",
              "GEOGRAPHY",
              "OTHER",
            ],
          },

          description: { type: "string" },

          sourcePages: {
            type: "array",
            items: { type: "integer" },
          },

          confidence: { type: "number" },
        },

        required: [
          "title",
          "category",
          "description",
          "sourcePages",
          "confidence",
        ],
      },
    },

    extractionMeta: {
      type: "object",

      properties: {
        warnings: {
          type: "array",
          items: { type: "string" },
        },

        conflicts: {
          type: "array",
          items: { type: "string" },
        },
      },

      required: ["warnings", "conflicts"],
    },
  },

  required: [
    "company",
    "business",
    "financials",
    "promoters",
    "risks",
    "extractionMeta",
  ],
};
```

---

# 25. The extraction prompt

Keep the prompt strict.

Example:

```ts
export const RHP_EXTRACTION_PROMPT = `
You are extracting structured information from an Indian IPO
Red Herring Prospectus (RHP).

RULES:

1. Use ONLY information contained in the attached RHP.

2. Do not use external knowledge.

3. Do not guess or estimate values.

4. If a requested value is not available:
   - value = null
   - status = "NOT_FOUND"
   - confidence should reflect that it was not located.

5. If different parts of the RHP contain materially conflicting
   values for the same metric:
   - status = "CONFLICTING"
   - include all relevant source pages in sourcePages
   - explain the conflict in extractionMeta.conflicts.

6. Preserve the actual financial year labels from the document.

7. Normalize Indian financial values into INR crore when sensible,
   but state the resulting unit explicitly.

8. Never interpret a missing promoter pledge disclosure as 0%.

9. Never invent source page numbers.

10. sourcePages must refer to PDF page numbers visible/identifiable
    from the supplied document.

11. Keep evidence snippets short.

12. Financial values must be taken from restated financial statements,
    audited financial information, KPI tables, or clearly identified
    issuer disclosures wherever possible.

13. If EBITDA is adjusted/non-standard, identify that distinction.

14. Do not calculate CAGR, valuation, technical indicators,
    stop-losses, position sizes, or current market data.

15. For risks, extract the most financially/materially relevant risks
    rather than copying every risk factor.

16. Government benefits must be based only on statements in this RHP.

Return only data matching the supplied JSON schema.
`;
```

---

# 26. Call Gemini with the RHP and structured output

Using `generateContent`:

```ts
import {
  createPartFromUri,
  createUserContent,
} from "@google/genai";

import { gemini } from "@/lib/gemini";
import { ipoExtractionJsonSchema } from "../schema/ipo-extraction.schema";
import { RHP_EXTRACTION_PROMPT } from "../prompts/rhp-extraction.prompt";

export async function extractRhpWithGemini(params: {
  fileUri: string;
  mimeType: string;
}) {
  const response = await gemini.models.generateContent({
    model: "gemini-2.5-flash-lite",

    contents: createUserContent([
      createPartFromUri(
        params.fileUri,
        params.mimeType
      ),

      RHP_EXTRACTION_PROMPT,
    ]),

    config: {
      responseMimeType: "application/json",
      responseSchema: ipoExtractionJsonSchema,

      // Extraction should be conservative.
      temperature: 0.1,
    },
  });

  if (!response.text) {
    throw new Error("Gemini returned an empty response");
  }

  return JSON.parse(response.text);
}
```

The exact SDK surface can evolve, so pin your package version in production and test upgrades before deployment.

---

# 27. Validate Gemini's response again on your server

Schema-constrained output is not a substitute for application validation.

Use Zod.

Example:

```ts
import { z } from "zod";

const evidenceNumber = z.object({
  value: z.number().nullable(),
  unit: z.string().nullable(),
  sourcePages: z.array(z.number().int().positive()),
  confidence: z.number().min(0).max(1),
  evidence: z.string().nullable(),

  status: z.enum([
    "FOUND",
    "NOT_FOUND",
    "AMBIGUOUS",
    "CONFLICTING",
    "NOT_APPLICABLE",
  ]),
});

export const ipoExtractionSchema = z.object({
  company: z.object({
    name: z.string().nullable(),
    industry: z.string().nullable(),
    description: z.string().nullable(),
    productsServices: z.array(z.string()),
  }),

  financials: z.array(
    z.object({
      financialYear: z.string(),
      revenueFromOperations: evidenceNumber,
      profitAfterTax: evidenceNumber,
      financeCosts: evidenceNumber,
      operatingCashFlow: evidenceNumber,
      tradeReceivables: evidenceNumber,
      totalBorrowings: evidenceNumber,
      totalEquity: evidenceNumber,
    })
  ),

  // Add the remaining sections here.
});
```

Then:

```ts
const parsed = ipoExtractionSchema.safeParse(rawOutput);

if (!parsed.success) {
  console.error(parsed.error.flatten());

  throw new Error(
    "Gemini JSON did not pass server-side validation"
  );
}

return parsed.data;
```

---

# 28. Build semantic validation rules

A JSON response can be structurally valid and still be economically wrong.

Create business rules.

Examples:

```ts
function validateFinancialYears(financials: any[]) {
  const issues: string[] = [];

  const years = financials.map((x) => x.financialYear);

  if (new Set(years).size !== years.length) {
    issues.push("Duplicate financial years");
  }

  return issues;
}
```

Other rules:

```text
Revenue should generally not be negative.

PAT can be negative.

Trade receivables should not normally be negative.

Total debt should not normally be negative.

Promoter holding should be 0–100%.

Pledge percentage should be 0–100%.

Page numbers must be positive integers.

FOUND values should normally have at least one source page.

NOT_FOUND values should be null.

A value with confidence < threshold should be queued for verification.
```

---

# 29. Recommended confidence thresholds

Treat model confidence as a signal, not mathematical truth.

A reasonable application policy:

```text
>= 0.95
AUTO_ACCEPT if all validation rules pass

0.85–0.949
ACCEPT for low-risk narrative fields
VERIFY important financial fields

0.70–0.849
VERIFY

< 0.70
REPROCESS / FLAG
```

For critical fields, be more conservative.

Critical fields:

```text
issue size
fresh issue
OFS
revenue
PAT
debt
equity
cash flow
promoter holding
price band
share count
```

---

# 30. Use a second pass only for questionable fields

Do not send the entire RHP through the expensive model again automatically.

Suppose the first pass produces:

```text
Revenue FY26 -> confidence 0.99
PAT FY26 -> confidence 0.97
Debt FY26 -> confidence 0.71
Promoter holding -> confidence 0.96
```

Only verify debt.

Construct a focused verification request:

```text
Verify the FY2026 total borrowings/debt value.

First-pass result:
₹438.2 crore

Reported source pages:
341, 348

Return:
- verified value
- unit
- source pages
- whether first-pass result is correct
- explanation if incorrect
```

You can use:

```text
gemini-2.5-flash
```

for this pass.

---

# 31. Verification design

Create:

```ts
type VerificationResult = {
  field: string;
  firstPassValue: number | string | null;
  verifiedValue: number | string | null;
  matches: boolean;
  sourcePages: number[];
  confidence: number;
  explanation: string | null;
};
```

Then your database can keep:

```text
extractedValue
verifiedValue
verificationStatus
verifiedByModel
verifiedAt
```

This is valuable if IPO Dekho will display financial information to users.

---

# 32. Backend calculations

Do not use Gemini for these.

## CAGR

```ts
export function cagr(
  start: number,
  end: number,
  years: number
) {
  if (start <= 0 || end < 0 || years <= 0) {
    return null;
  }

  return Math.pow(end / start, 1 / years) - 1;
}
```

Example:

```ts
const salesCagr = cagr(
  fy2024.revenue,
  fy2026.revenue,
  2
);
```

Be careful:

FY2024 -> FY2026 has **two growth intervals**, not three.

---

# 33. Profit CAGR caveat

If the starting PAT is:

```text
zero
negative
```

ordinary CAGR becomes misleading or undefined.

Store:

```text
profitCagr = null
profitCagrReason = "START_VALUE_NON_POSITIVE"
```

Do not force a percentage.

---

# 34. Debt-to-equity

```ts
export function debtToEquity(
  totalDebt: number,
  totalEquity: number
) {
  if (totalEquity === 0) return null;

  return totalDebt / totalEquity;
}
```

Define exactly what your product considers `totalDebt`.

For example:

```text
current borrowings
+ non-current borrowings
```

Do not silently mix lease liabilities unless you explicitly define your methodology that way.

---

# 35. Interest coverage

A common definition is:

```text
EBIT / finance cost
```

or sometimes issuer KPIs use a different definition.

Store both:

```text
reportedInterestCoverage
calculatedInterestCoverage
```

and document your formula.

---

# 36. Receivable trend

You can calculate:

```text
receivables / revenue
```

and, if suitable inputs exist:

```text
receivableDays =
averageTradeReceivables / revenue * 365
```

Be consistent about:

- opening receivables;
- closing receivables;
- average receivables.

If only year-end receivables are available, clearly label the approximation.

---

# 37. Operating cash flow quality

Useful calculated fields:

```text
OCF / PAT
OCF margin
3-year cumulative OCF
3-year cumulative PAT
```

Example:

```ts
const cashConversion =
  pat === 0
    ? null
    : operatingCashFlow / pat;
```

These are deterministic and cheap.

---

# 38. Separate RHP data from live/external data

The following should normally come from the RHP:

```text
company description
business model
products/services
competitive strengths
risk factors
financial statements
promoters
objects of issue
customer concentration
capacity
manufacturing facilities
restated KPIs
RHP peer table
RHP-mentioned government schemes
```

The following should come from external/current sources:

```text
current GMP
live subscription
latest QIB/NII/Retail subscription
allotment status
current market price
listing price
post-listing return
current P/E
current peer P/E
live market cap
technical chart structure
entry trigger
stop-loss
position quantity
current government-policy developments
```

Store a provenance field.

Example:

```ts
type DataSource =
  | "RHP"
  | "NSE"
  | "BSE"
  | "MARKET_API"
  | "CALCULATED"
  | "MANUAL";
```

---

# 39. Suggested database model

A simplified conceptual model:

```text
Ipo
IpoDocument
IpoExtractionRun
IpoFinancialYear
IpoMetric
IpoRisk
IpoPromoter
IpoPeer
IpoCustomerConcentration
IpoObjectOfIssue
IpoVerification
IpoProcessingJob
```

---

# 40. Example Prisma models

This is intentionally simplified.

```prisma
model IpoDocument {
  id              String   @id @default(cuid())
  ipoId           String
  documentType    String
  originalUrl     String?
  storageKey      String
  sha256          String   @unique
  fileSizeBytes   BigInt?

  geminiFileName  String?
  geminiFileUri   String?

  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt

  extractionRuns  IpoExtractionRun[]
}

model IpoExtractionRun {
  id               String   @id @default(cuid())
  documentId       String

  model             String
  schemaVersion     String
  promptVersion     String

  status            String

  rawJson           Json?
  validationErrors  Json?
  warnings          Json?

  inputTokens       Int?
  outputTokens      Int?
  estimatedCostUsd  Decimal?

  startedAt         DateTime @default(now())
  completedAt       DateTime?

  document          IpoDocument
    @relation(fields: [documentId], references: [id])
}

model IpoMetric {
  id             String   @id @default(cuid())
  ipoId          String

  metric         String
  financialYear  String?

  numericValue   Decimal?
  stringValue    String?
  unit           String?

  source         String

  sourcePages    Json?
  confidence     Decimal?
  evidence       String?
  status         String

  model          String?
  extractionRunId String?

  createdAt      DateTime @default(now())
}
```

---

# 41. Version your prompt and schema

This is very important.

Never just overwrite your production prompt.

Use:

```text
RHP_PROMPT_V1
RHP_PROMPT_V2
RHP_PROMPT_V3
```

and:

```text
IPO_SCHEMA_V1
IPO_SCHEMA_V2
```

Store both on every extraction run.

Then if you later discover:

> V2 was incorrectly interpreting borrowings.

you can identify exactly which IPOs were processed with V2 and reprocess only those.

---

# 42. Store the raw Gemini JSON

Keep:

```text
rawJson
```

even after normalizing data into tables.

Why?

Because if your database mapper has a bug, you can rerun normalization without paying Gemini again.

Recommended flow:

```text
Gemini
   |
   v
rawJson
   |
   v
schema validation
   |
   v
normalized DB rows
```

---

# 43. Token and cost logging

Record usage whenever the SDK/API exposes it.

Store:

```text
model
inputTokens
outputTokens
cachedTokens
requestCount
estimatedCostUsd
```

Create a daily aggregation:

```text
date
documentsProcessed
GeminiCalls
inputTokens
outputTokens
estimatedCost
verificationCalls
failedJobs
```

This will let you see your real cost per IPO.

---

# 44. Current Gemini 2.5 Flash-Lite pricing assumption

At the time this guide was prepared, Google lists standard paid pricing for:

```text
gemini-2.5-flash-lite
```

at approximately:

```text
Input:  $0.10 / 1M tokens
Output: $0.40 / 1M tokens
```

Pricing changes, so never hard-code pricing permanently.

Create configuration:

```ts
const MODEL_PRICING = {
  "gemini-2.5-flash-lite": {
    inputPerMillionUsd: 0.10,
    outputPerMillionUsd: 0.40,
  },

  "gemini-2.5-flash": {
    inputPerMillionUsd: 0.30,
    outputPerMillionUsd: 2.50,
  },
};
```

Review Google's pricing page periodically.

---

# 45. Cost calculation helper

```ts
type Usage = {
  inputTokens: number;
  outputTokens: number;
};

export function estimateCostUsd(
  usage: Usage,
  model: keyof typeof MODEL_PRICING
) {
  const pricing = MODEL_PRICING[model];

  return (
    (usage.inputTokens / 1_000_000) *
      pricing.inputPerMillionUsd
    +
    (usage.outputTokens / 1_000_000) *
      pricing.outputPerMillionUsd
  );
}
```

This is for your internal monitoring only.

Your billing provider's actual charge is authoritative.

---

# 46. Do not call Gemini whenever a user opens an IPO page

Wrong:

```text
User opens IPO
     |
     v
Send 800-page RHP to Gemini
     |
     v
wait
```

Correct:

```text
RHP becomes available
     |
     v
Background processing
     |
     v
Store extraction in DB

Later...

User opens IPO
     |
     v
Read PostgreSQL
     |
     v
instant response
```

Each RHP should normally be fully processed only once per extraction version.

---

# 47. Railway processing strategy

At 2–5 RHPs per day, you do not need Kafka or complicated infrastructure.

A simple architecture:

```text
Railway Web Service
       |
       v
PostgreSQL

Railway Worker
       |
       v
processing_jobs table
```

The API inserts a job:

```text
QUEUED
```

The worker claims it and changes it to:

```text
PROCESSING
```

Then:

```text
COMPLETED
FAILED
NEEDS_REVIEW
```

---

# 48. Example processing job table

```prisma
model IpoProcessingJob {
  id            String   @id @default(cuid())

  ipoId         String
  documentId    String

  type          String
  status        String

  attempts      Int      @default(0)
  maxAttempts   Int      @default(3)

  lockedAt      DateTime?
  lockedBy      String?

  nextAttemptAt DateTime?

  errorMessage  String?

  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt
}
```

This is enough for your current scale.

You can migrate to Redis/BullMQ later if necessary.

---

# 49. Worker loop

Conceptually:

```ts
while (true) {
  const job = await claimNextJob();

  if (!job) {
    await sleep(5000);
    continue;
  }

  try {
    await processRhp(job);

    await markCompleted(job.id);
  } catch (error) {
    await handleFailure(job, error);
  }
}
```

Make job claiming atomic so two Railway workers cannot process the same RHP simultaneously.

---

# 50. Full processing function

Conceptually:

```ts
export async function processRhp(job: ProcessingJob) {
  // 1.
  const document = await getDocument(job.documentId);

  // 2.
  const localPath =
    await obtainLocalPdf(document.storageKey);

  // 3.
  let geminiFile;

  if (document.geminiFileName) {
    geminiFile =
      await tryGetExistingGeminiFile(
        document.geminiFileName
      );
  }

  // 4.
  if (!geminiFile) {
    geminiFile =
      await uploadRhpToGemini(localPath);

    await saveGeminiFileInfo(
      document.id,
      geminiFile
    );
  }

  // 5.
  const readyFile =
    await waitForGeminiFile(
      geminiFile.name!
    );

  // 6.
  const raw =
    await extractRhpWithGemini({
      fileUri: readyFile.uri!,
      mimeType:
        readyFile.mimeType ??
        "application/pdf",
    });

  // 7.
  const parsed =
    validateExtraction(raw);

  // 8.
  const validationIssues =
    runBusinessValidation(parsed);

  // 9.
  await saveRawExtraction(
    document.id,
    parsed,
    validationIssues
  );

  // 10.
  const verificationRequests =
    findFieldsNeedingVerification(
      parsed,
      validationIssues
    );

  // 11.
  const verificationResults =
    await verifyCriticalFields(
      verificationRequests,
      readyFile
    );

  // 12.
  const finalData =
    applyVerificationResults(
      parsed,
      verificationResults
    );

  // 13.
  const calculatedMetrics =
    calculateFinancialMetrics(
      finalData
    );

  // 14.
  await normalizeAndSave(
    finalData,
    calculatedMetrics
  );
}
```

---

# 51. Retry strategy

Do not blindly retry every error immediately.

Classify failures.

## Retryable

```text
429 rate limit
5xx Gemini error
temporary network failure
temporary PDF processing error
timeout
```

Use exponential backoff:

```text
Attempt 1 -> 30 seconds
Attempt 2 -> 2 minutes
Attempt 3 -> 10 minutes
```

## Usually not retryable without intervention

```text
invalid PDF
HTML downloaded instead of PDF
corrupt document
schema programming error
missing required app configuration
```

---

# 52. Idempotency

Every production pipeline should be idempotent.

Key:

```text
document SHA256
+ extraction schema version
+ prompt version
+ model
```

For example:

```text
sha256:
ABC

schema:
IPO_SCHEMA_V3

prompt:
RHP_PROMPT_V4

model:
gemini-2.5-flash-lite
```

If a successful extraction already exists with those values, do not pay to run it again.

---

# 53. RHP revision handling

Sometimes an issuer can have:

```text
DRHP
updated DRHP
RHP
corrigendum
addendum
```

Do not overwrite all of these as if they are the same file.

Use document types:

```text
DRHP
RHP
CORRIGENDUM
ADDENDUM
OTHER
```

Your displayed IPO data should generally indicate the source/version.

---

# 54. Page-number problem

PDF page indices and printed page numbers can differ.

For example:

```text
PDF viewer page: 347
Printed document page: 319
```

Decide what `sourcePages` means.

My recommendation:

```text
sourcePages = PDF viewer page index, 1-based
```

because it is easiest for your application to open the exact PDF page.

If you also want printed document page labels, store:

```text
pdfPage
documentPageLabel
```

Do not mix the two.

---

# 55. Evidence verification UI

For admin users, create a review screen:

```text
Metric
Value
Confidence
Source page
Evidence
Verification status
```

Example:

```text
Revenue FY26
₹729.53 Cr
0.99
Page 287
"Revenue from operations..."
AUTO_ACCEPTED
```

Clicking the page number should open the RHP near that page.

This will massively reduce the effort required to spot extraction errors.

---

# 56. What should trigger manual review

I would flag an IPO when:

```text
critical financial field missing
financial years missing
revenue conflict
PAT conflict
debt conflict
promoter holding conflict
issue-size conflict
more than X low-confidence critical fields
schema validation failure
unexpected number of financial periods
PDF is scanned/poor quality
```

You should not manually review every field of every IPO.

Review exceptions.

---

# 57. Example validation scoring

Create an extraction quality score.

Example:

```text
100 points total

Critical financial completeness      30
Source-page coverage                  20
Confidence                            15
Promoter data                         10
IPO issue data                        10
No conflicts                          10
Business description                  5
```

Then:

```text
95–100  READY
85–94   READY_WITH_WARNINGS
70–84   VERIFY
<70     MANUAL_REVIEW
```

The exact weights are up to you.

---

# 58. Keep LLM work separate from calculations

Your final database object could contain:

```json
{
  "extracted": {
    "revenueFY24": 364.97,
    "revenueFY25": 466.47,
    "revenueFY26": 729.53,
    "patFY24": 37.17,
    "patFY25": 37.56,
    "patFY26": 62.34
  },

  "calculated": {
    "salesCagr": 0.4137,
    "profitCagr": 0.2951
  }
}
```

Never ask Gemini to produce the canonical calculated values if your backend can calculate them.

---

# 59. Do not store percentages ambiguously

Choose one convention.

I recommend storing ratios internally as decimal fractions:

```text
18.4% -> 0.184
```

UI:

```text
0.184 -> "18.40%"
```

Do not sometimes store:

```text
18.4
```

and sometimes:

```text
0.184
```

---

# 60. Currency normalization

RHPs can use:

```text
₹ million
₹ lakh
₹ crore
INR million
```

Pick one canonical unit.

For Indian IPO data, this is convenient:

```text
INR_CRORE
```

Example:

```text
₹ 7,295.3 million
```

becomes:

```text
₹729.53 crore
```

But keep:

```text
originalValue
originalUnit
normalizedValue
normalizedUnit
```

for critical financial values if you want maximum auditability.

---

# 61. Suggested metric storage

Example:

```json
{
  "metric": "REVENUE_FROM_OPERATIONS",
  "financialYear": "FY2026",

  "originalValue": 7295.3,
  "originalUnit": "INR_MILLION",

  "normalizedValue": 729.53,
  "normalizedUnit": "INR_CRORE",

  "source": "RHP",
  "sourcePages": [287],

  "confidence": 0.99,

  "status": "FOUND"
}
```

---

# 62. Start small

Do not build the final 200-field extractor immediately.

### Version 1

Extract:

```text
Company name
Business description
Products/services
Industry
Growth drivers
Competitive strengths

Revenue - 3 years
PAT - 3 years
Finance cost - 3 years
OCF - 3 years
Trade receivables - 3 years
Debt - 3 years
Equity - 3 years

Promoter names
Pre-issue holding
Post-issue holding
Pledge disclosure

Top-customer concentration

Issue size
Fresh issue
OFS
Objects of issue

Peers

10–15 most material risks
```

Get this accurate first.

---

# 63. Version 2

Then add:

```text
EBITDA
working capital
inventory
capacity utilization
manufacturing facilities
segment revenue
geographic revenue
supplier concentration
related-party transactions
litigation
contingent liabilities
order book
capex
government benefits
employee metrics
customer retention
```

---

# 64. Version 3

Then add your investor-analysis layer:

```text
quality score
growth score
balance-sheet score
cash-flow score
customer-concentration score
valuation score
governance score
risk score
overall IPO score
```

Those should be computed from normalized source data as much as possible.

Do not let one unrestricted LLM prompt generate the final investment score.

---

# 65. Testing before production

Build a golden test set of approximately 10–20 RHPs covering:

```text
manufacturing
financial services
consumer
pharma
technology
SME IPO
mainboard IPO
profit-making company
loss-making company
high debt
low debt
large OFS
pure fresh issue
scanned/difficult PDF
```

For every RHP, manually verify your most important fields.

---

# 66. Regression testing

Create:

```text
test-fixtures/
├── ipo-a.expected.json
├── ipo-b.expected.json
├── ipo-c.expected.json
└── ...
```

When changing:

```text
prompt
schema
model
normalization code
calculation code
```

rerun the test suite.

Compare:

```text
exact numeric accuracy
field completeness
source-page accuracy
conflict handling
```

---

# 67. Evaluation metrics

Measure:

## Numeric field accuracy

```text
correct extracted numeric fields /
total verified numeric fields
```

## Source-page accuracy

```text
correct source pages /
total checked source pages
```

## Completeness

```text
correctly filled expected fields /
fields available in RHP
```

## False-fill rate

Very important:

```text
fields AI filled even though
the value was not actually supported
```

Your goal should be an extremely low false-fill rate.

For finance, missing is better than fabricated.

---

# 68. Security

Do:

```text
keep Gemini key server-side
restrict production secrets
rotate compromised keys
log request IDs
validate downloaded PDFs
limit file size
sanitize filenames
use storage-generated object keys
```

Do not:

```text
trust user-supplied MIME type
serve private storage credentials
put Gemini API key in React Native
put Gemini API key in browser JavaScript
log API keys
```

---

# 69. Privacy/data handling

RHPs are public documents, so the privacy profile is much simpler than processing private company records.

Still:

- use your own permanent storage;
- keep processing logs;
- understand the Gemini API data terms for the billing tier you choose;
- avoid sending unrelated private application data with the RHP.

---

# 70. Observability

Log per processing run:

```text
IPO ID
document ID
SHA256
model
prompt version
schema version
Gemini file ID
started time
finished time
duration
input/output token usage
validation score
verification count
final status
error type
```

Use structured logs.

Example:

```json
{
  "event": "ipo_rhp_extraction_completed",
  "ipoId": "ipo_123",
  "documentId": "doc_456",
  "model": "gemini-2.5-flash-lite",
  "schemaVersion": "v1",
  "qualityScore": 97,
  "verificationCount": 2
}
```

---

# 71. Monitoring

At minimum monitor:

```text
jobs queued
jobs failed
jobs stuck
average processing duration
Gemini 429 rate
Gemini 5xx rate
average cost per RHP
verification percentage
manual-review percentage
```

If:

```text
verification percentage suddenly jumps
```

after a prompt/model change, you probably introduced a regression.

---

# 72. Production processing statuses

Use explicit states:

```text
DISCOVERED
DOWNLOADING
DOWNLOADED
UPLOADING_TO_GEMINI
GEMINI_PROCESSING
EXTRACTING
VALIDATING
VERIFYING
CALCULATING
READY
READY_WITH_WARNINGS
NEEDS_REVIEW
FAILED
```

This will make your admin dashboard much easier to understand.

---

# 73. Complete simplified implementation

This is a compact end-to-end example.

```ts
import {
  GoogleGenAI,
  createPartFromUri,
  createUserContent,
} from "@google/genai";

const ai = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY!,
});

const sleep = (ms: number) =>
  new Promise((resolve) => setTimeout(resolve, ms));

export async function processLocalRhp(
  filePath: string
) {
  // ---------------------------------
  // 1. Upload PDF
  // ---------------------------------

  const uploaded = await ai.files.upload({
    file: filePath,
    config: {
      mimeType: "application/pdf",
    },
  });

  if (!uploaded.name) {
    throw new Error("Upload returned no file name");
  }

  // ---------------------------------
  // 2. Wait for document processing
  // ---------------------------------

  let file = await ai.files.get({
    name: uploaded.name,
  });

  while (file.state === "PROCESSING") {
    await sleep(2000);

    file = await ai.files.get({
      name: uploaded.name,
    });
  }

  if (file.state === "FAILED") {
    throw new Error("Gemini PDF processing failed");
  }

  if (!file.uri) {
    throw new Error("Processed file has no URI");
  }

  // ---------------------------------
  // 3. Run structured extraction
  // ---------------------------------

  const response = await ai.models.generateContent({
    model: "gemini-2.5-flash-lite",

    contents: createUserContent([
      createPartFromUri(
        file.uri,
        file.mimeType ?? "application/pdf"
      ),

      `
      Extract the requested IPO RHP data.

      Use only the PDF.

      Never guess.

      Missing data must be null.

      Include source pages for all material
      financial and promoter fields.

      Do not calculate CAGR or current valuation.
      `,
    ]),

    config: {
      responseMimeType: "application/json",
      responseSchema: ipoExtractionJsonSchema,
      temperature: 0.1,
    },
  });

  if (!response.text) {
    throw new Error("No model response");
  }

  // ---------------------------------
  // 4. Parse
  // ---------------------------------

  const raw = JSON.parse(response.text);

  // ---------------------------------
  // 5. Validate
  // ---------------------------------

  const parsed =
    ipoExtractionSchema.parse(raw);

  // ---------------------------------
  // 6. Run application validations
  // ---------------------------------

  const issues =
    runBusinessValidation(parsed);

  // ---------------------------------
  // 7. Verify questionable fields
  // ---------------------------------

  const fieldsToVerify =
    findFieldsNeedingVerification(
      parsed,
      issues
    );

  // ---------------------------------
  // 8. Calculate deterministic metrics
  // ---------------------------------

  const calculated =
    calculateFinancialMetrics(parsed);

  return {
    extracted: parsed,
    calculated,
    validationIssues: issues,
    fieldsToVerify,
  };
}
```

---

# 74. First local test

Create:

```text
scripts/test-rhp.ts
```

```ts
import "dotenv/config";
import { processLocalRhp }
  from "../src/ipo/services/process-rhp";

async function main() {
  const result = await processLocalRhp(
    "./samples/test-rhp.pdf"
  );

  console.dir(result, {
    depth: null,
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

Run:

```bash
npx tsx scripts/test-rhp.ts
```

Install `tsx` if needed:

```bash
npm install -D tsx
```

---

# 75. Railway deployment

A simple Railway project can contain:

```text
Service 1
IPO Dekho API

Service 2
RHP Worker

Service 3
PostgreSQL
```

Object storage can remain external.

The web/API service should:

```text
discover/register RHP
download/store PDF
create processing job
serve completed IPO data
```

The worker should:

```text
claim processing job
upload to Gemini
extract
validate
verify
calculate
save
complete job
```

---

# 76. Environment variables

Example:

```env
DATABASE_URL=postgresql://...

GEMINI_API_KEY=...

R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=ipo-rhp
R2_ENDPOINT=...

RHP_PRIMARY_MODEL=gemini-2.5-flash-lite
RHP_FALLBACK_MODEL=gemini-2.5-flash

RHP_SCHEMA_VERSION=v1
RHP_PROMPT_VERSION=v1
```

---

# 77. Recommended production strategy

For every new RHP:

```text
1. Download.

2. Confirm it is actually a PDF.

3. Calculate SHA-256.

4. Check if already processed.

5. Save original to R2/S3.

6. Create DB document record.

7. Create processing job.

8. Worker uploads PDF to Gemini Files API.

9. Wait for Gemini document processing.

10. Send RHP + strict extraction prompt +
    JSON schema to gemini-2.5-flash-lite.

11. Parse JSON.

12. Validate with Zod.

13. Run financial/business validation rules.

14. Identify low-confidence critical fields.

15. Verify only those fields.

16. Calculate all deterministic metrics locally.

17. Normalize and save data to PostgreSQL.

18. Calculate extraction-quality score.

19. Mark:
    READY,
    READY_WITH_WARNINGS,
    or NEEDS_REVIEW.

20. IPO Dekho reads stored data from PostgreSQL.
```

---

# 78. What you should NOT do initially

Avoid:

```text
Vector database
RAG
Embeddings
Fine-tuning
Local LLM
GPU server
Hermes agent
One prompt per RHP page
Hundreds of chunk-level requests
Repeated LLM processing on every user request
```

At 2–5 RHPs/day these add complexity without a strong payoff.

---

# 79. Where RAG could become useful later

RAG may eventually make sense for a different feature:

> User asks arbitrary questions about an old IPO/RHP.

For example:

```text
"What is this company's dependence on China?"
```

across thousands of stored RHPs.

That is a search/query product.

Your current problem is different:

> Extract a known set of fields from each new RHP once.

For this, direct structured extraction is simpler.

---

# 80. Suggested first milestone

Do not start by building every requested IPO metric.

Build this first:

```text
INPUT

One RHP PDF


OUTPUT

Company
Industry
Description
Products
Competitive strengths
Growth drivers

FY24 revenue
FY25 revenue
FY26 revenue

FY24 PAT
FY25 PAT
FY26 PAT

FY24 OCF
FY25 OCF
FY26 OCF

FY24 debt
FY25 debt
FY26 debt

FY24 receivables
FY25 receivables
FY26 receivables

Promoter holding

Customer concentration

Fresh issue
OFS
Objects of issue

10 key risks

All critical values with source pages.
```

Then manually verify 10 RHPs.

Only after accuracy is satisfactory should you expand.

---

# 81. Suggested second milestone

Add deterministic calculations:

```text
3Y sales CAGR
3Y PAT CAGR
Debt/equity
OCF/PAT
receivable trend
PAT margin
revenue growth
cash conversion
```

---

# 82. Suggested third milestone

Integrate external sources:

```text
NSE
BSE
market data
subscription data
listing data
```

Then produce:

```text
Current P/E
Peer P/E
Subscription
Listing gain
Current return
```

---

# 83. Suggested fourth milestone

Build the final IPO analysis engine.

Your user-facing structure can become:

```text
Company
Industry

What the company sells

Why customers choose it

Growth triggers

3Y sales CAGR
3Y PAT CAGR

ROCE
Debt/equity
Interest coverage
3Y operating cash flow

Promoter holding
Promoter pledge

Customer concentration
Receivable trend

Valuation

Peers

Risks

Government benefit/tailwinds

IPO use of proceeds

Final quality summary
```

But every displayed statement should retain its provenance.

---

# 84. Provenance example

Your API response can expose:

```json
{
  "salesCagr": {
    "value": 0.4137,
    "display": "41.37%",
    "source": "CALCULATED",
    "inputs": [
      {
        "metric": "REVENUE_FROM_OPERATIONS",
        "year": "FY2024",
        "value": 364.97,
        "source": "RHP",
        "sourcePages": [287]
      },
      {
        "metric": "REVENUE_FROM_OPERATIONS",
        "year": "FY2026",
        "value": 729.53,
        "source": "RHP",
        "sourcePages": [287]
      }
    ]
  }
}
```

This is the type of architecture that makes an IPO research product trustworthy.

---

# 85. Final recommendation

For your current volume:

```text
2–5 RHPs per day
```

use this stack:

```text
PDF storage:
Cloudflare R2 / S3

Primary extraction:
gemini-2.5-flash-lite

Fallback verification:
gemini-2.5-flash

AI file transport:
Gemini Files API

Output:
Strict JSON Schema

Runtime validation:
Zod

Database:
PostgreSQL

Worker:
Railway background worker

Calculations:
TypeScript backend

RAG:
No

Embeddings:
No

Fine-tuning:
No
```

The biggest determinants of reliability will be:

1. your extraction schema;
2. your prompt rules;
3. source-page/evidence capture;
4. deterministic calculations;
5. validation;
6. selective second-pass verification;
7. prompt/schema versioning;
8. regression testing.

The model itself is only one part of the system.

---

# 86. Official references

Current Google documentation used when preparing this guide:

- Gemini API getting started  
  https://ai.google.dev/gemini-api/docs/get-started

- Google GenAI SDK migration guide  
  https://ai.google.dev/gemini-api/docs/migrate

- Gemini Files API / file input methods  
  https://ai.google.dev/gemini-api/docs/file-input-methods

- Gemini document/PDF understanding  
  https://ai.google.dev/gemini-api/docs/document-processing

- Structured outputs  
  https://ai.google.dev/gemini-api/docs/structured-output

- Gemini API pricing  
  https://ai.google.dev/gemini-api/docs/pricing

---

# 87. Implementation checklist

- [ ] Create Gemini API key.
- [ ] Add `GEMINI_API_KEY` to Railway.
- [ ] Install `@google/genai`.
- [ ] Install `zod`.
- [ ] Create permanent RHP bucket.
- [ ] Build RHP downloader.
- [ ] Validate `%PDF-` header.
- [ ] Calculate SHA-256.
- [ ] Deduplicate documents.
- [ ] Upload RHP to R2/S3.
- [ ] Upload processing copy to Gemini Files API.
- [ ] Wait for Gemini file state.
- [ ] Create IPO JSON Schema V1.
- [ ] Create RHP Prompt V1.
- [ ] Run `gemini-2.5-flash-lite`.
- [ ] Require structured JSON.
- [ ] Validate JSON with Zod.
- [ ] Store raw JSON.
- [ ] Run semantic validation.
- [ ] Flag low-confidence critical fields.
- [ ] Verify only questionable fields.
- [ ] Calculate CAGR and ratios in TypeScript.
- [ ] Normalize units.
- [ ] Save normalized metrics.
- [ ] Preserve source pages.
- [ ] Store model/prompt/schema versions.
- [ ] Record token usage/cost.
- [ ] Build processing job table.
- [ ] Deploy Railway worker.
- [ ] Build admin review screen.
- [ ] Create 10–20 RHP golden test set.
- [ ] Run extraction regression tests.
- [ ] Expand schema only after V1 is reliable.

---

**Document version:** 1.0  
**Prepared:** 22 August 2026  
