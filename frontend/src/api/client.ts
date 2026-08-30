import axios from 'axios';
import { useAuthStore } from '../stores/auth';
export const api=axios.create({baseURL:'/api/v1'});
api.interceptors.request.use(config=>{const token=useAuthStore.getState().accessToken;if(token)config.headers.Authorization=`Bearer ${token}`;return config});
let refreshing:Promise<string|null>|null=null;
api.interceptors.response.use(r=>r,async error=>{const original=error.config;if(error.response?.status===401&&original&&!original._retry&&useAuthStore.getState().refreshToken){original._retry=true;const refresh=useAuthStore.getState().refreshToken;refreshing??=(async()=>{try{const r=await axios.post<{access_token:string;refresh_token:string}>('/api/v1/auth/refresh',{refresh_token:refresh});useAuthStore.getState().setTokens(r.data.access_token,r.data.refresh_token);return r.data.access_token}catch{useAuthStore.getState().logout();return null}finally{refreshing=null}})();const token=await refreshing;if(token){original.headers.Authorization=`Bearer ${token}`;return api(original)}}return Promise.reject(error)});
