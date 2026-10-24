# Chat Insights — frontend

A React + TypeScript + Tailwind frontend for the chat-transcript analysis pipeline:
upload a transcript file → watch it move through the pipeline → browse the resulting
conversation clusters.

## Running it

```bash
npm install
npm run dev       # local dev server
npm run build     # production build → dist/
```

## How it's wired

This talks to the FastAPI server in `../backend/api_server.py`. Start that first:

```bash
cd ../backend && python api_server.py     # → localhost:8000
```

`vite.config.ts` proxies `/api` to port 8000 in development, so there's no base
URL or CORS setup needed locally. For a deployed build where the API is on a
different origin, set `VITE_API_BASE_URL`.

Every screen only ever calls the four functions in `src/api/backend.ts`:

```ts
uploadTranscript(file)
startPipeline(fileId)
getPipelineStatus(jobId)   // polled every 1.5s while a job is running
getAnalysisResults(jobId)
```

The progress bar reads a real `progress` value from the backend, weighted by how
long each pipeline step actually takes. It falls back to an indeterminate
animation if `progress` ever comes back `null`.

## Structure

```
src/
  api/backend.ts          ← the one file to swap for a real backend
  types/index.ts           ← shared TypeScript types
  utils/format.ts          ← byte size / timer / percent formatting
  components/
    WelcomeScreen.tsx       screen 1: upload
    FileUploader.tsx        drag-and-drop + browse
    FilePreview.tsx         "file selected" state
    PipelineProgress.tsx    screen 2: processing
    PipelineStepItem.tsx    single step in the timeline
    ResultsDashboard.tsx    screen 3: results
    SummaryCard.tsx         top-level stat card
    ClusterCard.tsx         one cluster in the grid
    ClusterDetails.tsx      drill-down drawer (tabs: overview/conversations/insights)
    ErrorState.tsx          shown if the pipeline fails
    LoadingState.tsx        small reusable spinner
  App.tsx                  orchestrates stage transitions + polling
```
