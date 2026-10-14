export const session = { get token() { return sessionStorage.getItem('vera-token') || '' }, set token(v: string) { if(v) sessionStorage.setItem('vera-token',v); else sessionStorage.removeItem('vera-token') } }
export async function request<T>(path: string, body?: unknown, html = false): Promise<T> {
  const r=await fetch(`/api/${path}`,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json',...(session.token?{Authorization:`Bearer ${session.token}`}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  if(!r.ok){const d=await r.json().catch(()=>({}));if(r.status===401)session.token='';throw new Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||r.statusText))}return html?await r.text() as T:await r.json() as T;
}
