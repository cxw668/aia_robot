import client from './client';

export interface IngestJob {
  job_id: string;
  type: 'dir' | 'url' | 'file';
  source: string;
  collection: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  created_at: string;
  doc_count: number;
  error?: string;
}

export interface KbCollection {
  name: string;
  doc_count: number;
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
  docs: KbDoc[];
  collection: string;
}

export interface HealthResponse {
  status: string;
  doc_count: number;
  collection: string;
  last_updated: string;
}

export async function ingestDir(path: string, collection: string): Promise<{ job_id: string; collection: string }> {
  const res = await client.post('/kb/ingest', { type: 'dir', path, collection });
  return res.data;
}

export async function ingestUrl(url: string, collection: string): Promise<{ job_id: string; collection: string }> {
  const res = await client.post('/kb/ingest', { type: 'url', url, collection });
  return res.data;
}

export async function uploadFile(file: File, collection: string): Promise<{ job_id: string; collection: string }> {
  const form = new FormData();
  form.append('file', file);
  const res = await client.post(`/kb/upload?collection=${encodeURIComponent(collection)}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getJobs(): Promise<IngestJob[]> {
  const res = await client.get<IngestJob[]>('/kb/jobs');
  return res.data;
}

export async function getCollections(): Promise<KbCollection[]> {
  const res = await client.get<{ collections: KbCollection[] }>('/kb/collections');
  return res.data.collections;
}

export async function deleteCollection(name: string): Promise<void> {
  await client.delete(`/kb/collections/${encodeURIComponent(name)}`);
}

export async function getDocs(
  params: { collection?: string; q?: string; limit?: number; offset?: number } = {}
): Promise<KbDocsResponse> {
  const res = await client.get<KbDocsResponse>('/kb/docs', { params });
  return res.data;
}

export async function deleteDoc(docId: string, collection: string): Promise<void> {
  await client.delete(`/kb/docs/${docId}?collection=${encodeURIComponent(collection)}`);
}

export async function getHealth(collection?: string): Promise<HealthResponse> {
  const res = await client.get<HealthResponse>('/health', { params: collection ? { collection } : {} });
  return res.data;
}
