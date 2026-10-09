import { Alert, Button, Input, Select, Space, Table, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { generateLoadBol, getLoadEvidence, resolveLoadException, reviewLoadEvidence } from '../api/loads'
import type { Load } from '../api/loads'
import { dispatchFailure, evidenceRefreshDelay } from './loadDispatchState'

export function LoadDispatchEvidence({load,canManage,onChanged}:{load:Load;canManage:boolean;onChanged?:()=>void}) {
  const qc=useQueryClient()
  const evidence=useQuery({queryKey:['load-evidence',load.id],queryFn:()=>getLoadEvidence(load.id),refetchInterval:q=>evidenceRefreshDelay(q.state.data)})
  const [note,setNote]=useState(''),[order,setOrder]=useState<number>(),[exception,setException]=useState<number>(),[errors,setErrors]=useState<string[]>([])
  const operations=useRef(new Map<string,string>())
  const action=useMutation({mutationFn:(perform:()=>Promise<unknown>)=>perform(),onSuccess:()=>{setErrors([]);['load-evidence','load-dispatch-readiness','load'].forEach(k=>void qc.invalidateQueries({queryKey:[k,load.id]}));onChanged?.()},onError:e=>setErrors(dispatchFailure(e))})
  const data=evidence.data
  const mutable=canManage && ['PLANNED','READY'].includes(load.status)
  const review=(c:any,decision:string)=>{
    const payload={kind:c.kind,decision,plan_id:data.plan_id,content_revision:data.content_revision,expected_fingerprint:c.fingerprint,note:note.trim()}
    const key=JSON.stringify(payload)
    if(!operations.current.has(key)) operations.current.set(key,crypto.randomUUID())
    action.mutate(async()=>{const result=await reviewLoadEvidence(load.id,{...payload,operation_id:operations.current.get(key)});operations.current.delete(key);return result})
  }
  return <Space direction="vertical" style={{width:'100%'}}>
    <Typography.Title level={5}>{load.dispatch_business_type==='FBA'?'FBA':'私仓'}单据、计划审批与异常复核</Typography.Title>
    {evidence.isError && <Alert type="error" message="证据读取失败" description={dispatchFailure(evidence.error).join('；')}/>}
    {data && <>
      <Alert type={data.configured?'info':'warning'} message={data.configured?`规则版本 ${data.policy.version}：${data.policy.source}`:'业务规则未配置或未启用，真实派发继续阻断'} description="页面操作不能启用规则。复核绑定当前计划、单据与异常内容；变化、过期或权限失效必须重新复核。预检通过仍须提交事务内派发校验。"/>
      {errors.length>0 && <Alert type="error" message="证据操作失败" description={errors.join('；')}/>}
      <Input.TextArea aria-label="复核或异常处理说明" placeholder="复核或异常处理说明（必填）" value={note} onChange={e=>setNote(e.target.value)} />
      {data.checks.map((c:any)=><Space key={c.kind} direction="vertical" style={{width:'100%'}}>
        <Alert type={c.status==='PASS'?'success':'warning'} message={`${c.kind} · ${c.status} · ${c.reason}`} description={<><div>处理权限：{c.roles?.join('、')||'尚未确认'}；{c.can_review?'当前用户可以复核':'当前用户无复核权限或计划未锁定'}</div>{c.missing?.map((m:string)=><div key={m}>{m}</div>)}{c.review && <div>复核人 #{c.review.actor_id}；计划 #{c.review.plan_id} 修订 {c.review.content_revision}；有效至 {c.review.expires_at}</div>}</>}/>
        <Space><Button disabled={!mutable || !c.can_review || !note.trim() || !!c.missing?.length || action.isPending} onClick={()=>review(c,'ACCEPT')}>确认 {c.kind}</Button><Button danger disabled={!mutable || !c.can_review || !note.trim() || action.isPending} onClick={()=>review(c,'REJECT')}>拒绝 {c.kind}</Button></Space>
      </Space>)}
      <Space wrap><Select aria-label="单据订单" placeholder="选择本派车单订单" style={{minWidth:240}} value={order} onChange={setOrder} options={(load.outbounds??[]).map(o=>({value:o.id,label:o.ob_no}))}/><Button disabled={!mutable || !order || action.isPending} onClick={()=>action.mutate(()=>generateLoadBol(load.id,order!))}>生成并登记 BOL</Button><Typography.Link href="/documents">上传、版本及归档管理</Typography.Link></Space>
      <Table size="small" pagination={false} rowKey="id" dataSource={data.documents} columns={[{title:'单据',dataIndex:'id'},{title:'类型',dataIndex:'document_type'},{title:'业务',dataIndex:'dispatch_business_type'},{title:'版本',dataIndex:'version'},{title:'状态',dataIndex:'status'},{title:'订单',dataIndex:'outbound_id'}]}/>
      <Space wrap><Select aria-label="关联异常" placeholder="选择关联的活动异常" style={{minWidth:240}} value={exception} onChange={setException} options={data.exceptions.filter((e:any)=>['OPEN','INVESTIGATING'].includes(e.status)).map((e:any)=>({value:e.id,label:`#${e.id} ${e.title??e.status}`}))}/><Button disabled={!mutable || !exception || !note.trim() || action.isPending} onClick={()=>action.mutate(()=>resolveLoadException(load.id,exception!,note.trim()))}>记录异常处理结果</Button></Space>
      <Typography.Text type="secondary">异常处理权限由服务端核对；处理后仍需具备规则授权的人员复核。所有历史结果保留。</Typography.Text>
      <Table size="small" pagination={false} rowKey="id" dataSource={data.exceptions} columns={[{title:'异常',dataIndex:'id'},{title:'状态',dataIndex:'status'},{title:'处理人',dataIndex:'resolved_by'},{title:'处理结果',dataIndex:'resolution'}]}/>
      <Table size="small" pagination={{pageSize:5}} rowKey="id" dataSource={data.history} columns={[{title:'复核',dataIndex:'kind'},{title:'结果',dataIndex:'decision'},{title:'人员',dataIndex:'actor_id'},{title:'计划',dataIndex:'plan_id'},{title:'规则',dataIndex:'policy_id'},{title:'有效至',dataIndex:'expires_at'},{title:'说明',dataIndex:'note'}]}/>
    </>}
  </Space>
}
