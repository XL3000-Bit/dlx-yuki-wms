import{api}from'./client';
export type UserPermission='read'|'manage_inbound'|'manage_outbound'|'manage_warehouse'|'manage_users';
export interface CurrentUser{id:number;username:string;display_name:string;email:string;role:string;is_active:boolean;permissions:UserPermission[];warehouse_scope_mode:'ALL'|'SELECTED';customer_scope_mode:'ALL'|'SELECTED';warehouse_ids:number[];customer_ids:number[]}
export async function login(username:string,password:string){return(await api.post<{access_token:string;refresh_token:string}>('/auth/login',{username,password})).data}
export async function getCurrentUser(){return(await api.get<CurrentUser>('/users/me')).data}
