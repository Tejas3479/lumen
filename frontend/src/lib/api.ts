import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';
import { useUserStore } from '@/store/userStore';
import toast from 'react-hot-toast';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// ─── Request interceptor — attach JWT ─────────────────────────
api.interceptors.request.use((config) => {
  const token = useUserStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Response interceptor — handle errors globally ────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const message: string =
      error.response?.data?.message ||
      error.response?.data?.detail ||
      'Something went wrong';

    if (status === 401) {
      useUserStore.getState().logout();
      toast.error('Session expired. Please log in again.');
    } else if (status === 429) {
      toast.error('Too many requests. Please slow down.');
    } else if (status >= 500) {
      toast.error('Server error. Please try again later.');
    }

    return Promise.reject({ status, message, data: error.response?.data });
  }
);

export default api;

// ─── Typed helpers ────────────────────────────────────────────
export const apiGet = <T>(url: string, config?: AxiosRequestConfig) =>
  api.get<T>(url, config).then((r) => r.data);

export const apiPost = <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
  api.post<T>(url, data, config).then((r) => r.data);

export const apiPut = <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
  api.put<T>(url, data, config).then((r) => r.data);

export const apiPatch = <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
  api.patch<T>(url, data, config).then((r) => r.data);

export const apiDelete = <T>(url: string, config?: AxiosRequestConfig) =>
  api.delete<T>(url, config).then((r) => r.data);

export const apiPostForm = <T>(url: string, data?: FormData, config?: AxiosRequestConfig) =>
  api.post<T>(url, data, {
    ...config,
    headers: {
      ...config?.headers,
      'Content-Type': 'multipart/form-data',
    },
  }).then((r) => r.data);
