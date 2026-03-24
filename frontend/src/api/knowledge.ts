import client from './client';

export interface IngestJob {
  job_id: string;
  type: 'dir' | 'url' | 'file';
  source: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  created_at: string;
  doc_count: number;
  error?: string;
}

export interface KbDoc {
  id: string;
  score: number | null;
  title: string;
  content: string;
  service_name: string;
  service_url?: string;
  source_file?: string;
  category?: string;
  schema?: string;
}

export interface KbDocsResponse {
  total: number;
  offset: number;
  limit: number;
  category: string | null;
  docs: KbDoc[];
}

export interface KbCategory {
  name: string;
  count: number;
}

export interface HealthResponse {
  status: string;
  doc_count: number;
  last_updated: string;
}

export async function ingestDir(path: string): Promise<{ job_id: string }> {
  const res = await client.post<{ job_id: string }>('/kb/ingest', { type: 'dir', path });
  return res.data;
}

export async function ingestUrl(url: string): Promise<{ job_id: string }> {
  const res = await client.post<{ job_id: string }>('/kb/ingest', { type: 'url', url });
  return res.data;
}

export async function uploadFile(file: File): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await client.post<{ job_id: string }>('/kb/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getJobs(): Promise<IngestJob[]> {
  const res = await client.get<IngestJob[]>('/kb/jobs');
  return res.data;
}

export async function getDocs(
  params: { q?: string; limit?: number; offset?: number } = {}
): Promise<KbDocsResponse> {
  const res = await client.get<KbDocsResponse>('/kb/docs', { params });
  return res.data;
}

export async function deleteDoc(docId: string): Promise<void> {
  await client.delete(`/kb/docs/${docId}`);
}

export async function deleteAllDocs(): Promise<void> {
  await client.delete('/kb/docs');
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await client.get<HealthResponse>('/health');
  return res.data;
}
