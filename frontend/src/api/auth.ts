import{api}from'./client';export async function login(username:string,password:string){return(await api.post<{access_token:string;refresh_token:string}>('/auth/login',{username,password})).data}
