import { Alert, Button, Form, InputNumber, Select, Space, Table, Typography, message } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { attachLoadOutbounds, classifyLoadOrder, createLoadPlan, finalizeLoadPlan, getLoadAllocations, getLoadExecution, getLoadPlans, replaceLoadPlanLines, updateLoadStatus, writeLoadAllocation, writeLoadExecution } from '../api/loads'
import { writeLoadPlanLines } from '../api/loads'
import type { BusinessType, Load, DispatchPlan } from '../api/loads'
import { dispatchFailure, dispatchRequest, sameDispatchDomain, openVerificationRun } from './loadDispatchState'
import { LoadDispatchEvidence } from './LoadDispatchEvidence'

function PlanLinesEditor({plan,editable,busy,onSave}:{plan:DispatchPlan;editable:boolean;busy:boolean;onSave:(lines:DispatchPlan['lines'])=>void}) {
  const [lines,setLines]=useState(plan.lines.map(line=>({...line})))
  const change=(id:number,field:'pallet_qty'|'carton_qty',value:number|null)=>setLines(previous=>previous.map(line=>line.allocation_id===id?{...line,[field]:value??0}:line))
  return <Space direction="vertical" style={{width:'100%'}}>
    <Table size="small" pagination={false} rowKey="allocation_id" dataSource={lines} columns={[
      {title:'计划分配 ID',dataIndex:'allocation_id'},
      ...(['pallet_qty','carton_qty'] as const).map(field=>({title:field==='pallet_qty'?'PLT':'CTN',key:field,render:(_:unknown,line:DispatchPlan['lines'][number])=><InputNumber aria-label={`计划分配 #${line.allocation_id} ${field==='pallet_qty'?'托盘':'箱'}数量`} min={0} value={Number(line[field])} disabled={!editable||busy} onChange={value=>change(line.allocation_id,field,value)}/>})),
    ]}/>
    <Button disabled={!editable||busy||!lines.length} onClick={()=>onSave(lines)}>保存计划内容</Button>
  </Space>
}

export function LoadDispatchWorkbench({load,businessType,canManage,onChanged}:{load:Load;businessType:BusinessType;canManage:boolean;onChanged?:()=>void}) {
  const qc=useQueryClient()
  const facts=useQuery({queryKey:['load-allocations',load.id],queryFn:()=>getLoadAllocations(load.id)})
  const plans=useQuery({queryKey:['load-plans',load.id],queryFn:()=>getLoadPlans(load.id)})
  const execution=useQuery({queryKey:['load-execution',load.id],queryFn:()=>getLoadExecution(load.id)})
  const [errors,setErrors]=useState<string[]>([])
  const [stageForm]=Form.useForm()
  // Retain operation ids after ambiguous failures, so retrying the same intent is safe.
  const operations=useRef(new Map<string,string>())
  const op=(key:string)=>{if(!operations.current.has(key)) operations.current.set(key,crypto.randomUUID());return operations.current.get(key)!}
  const action=useMutation({
    mutationFn:async ({key,perform}:{key:string;perform:()=>Promise<unknown>})=>({key,result:await perform()}),
    onSuccess:({key})=>{operations.current.delete(key);setErrors([]);message.success('已保存并核验');['load','loads','load-allocations','load-plans','load-execution','load-evidence','load-dispatch-readiness'].forEach(k=>qc.invalidateQueries({queryKey:k==='loads'?[k]:[k,load.id]}));onChanged?.()},
    onError:e=>{setErrors(dispatchFailure(e));['load-plans','load-execution','load-evidence','load-dispatch-readiness'].forEach(k=>void qc.invalidateQueries({queryKey:[k,load.id]}));onChanged?.()},
  })
  const execute=(key:string,perform:()=>Promise<unknown>)=>action.mutate({key,perform})
  const run=openVerificationRun(execution.data)
  const executionBusy=execution.isFetching || execution.isError
  const plan=plans.data?.[0]
  const mutable=canManage && ['PLANNED','READY'].includes(load.status)
  const editable=mutable && plan?.status!=='FINAL'
  if(!sameDispatchDomain(load,businessType)) return <Alert type="error" message="业务或订单归属不一致，操作已阻断" description="旧记录必须先明确业务类型；订单、库存与派车单必须属于同一仓库及业务。" />
  const reservations=(load.outbounds??[]).flatMap(o=>(o.inventory_allocations??[]).map((a:any)=>({...a,order:o})))
  const saveExecution=async(actionName:'stage'|'verify/scan')=>{
    const v=await stageForm.validateFields()
    if(actionName==='verify/scan'&&!run) throw new Error('请先开始装车核验')
    const key=JSON.stringify([actionName,v,run])
    execute(key,()=>writeLoadExecution(load.id,actionName,{...v,...(actionName==='verify/scan'?{verification_run_id:run}:{}),client_operation_id:op(key)}))
  }
  return <Space direction="vertical" style={{width:'100%'}}>
    <Typography.Title level={5}>{businessType==='FBA'?'FBA':'私仓'}派发工作台</Typography.Title>
    <Alert type="info" message="先分配已有库存预留，再创建、核对并锁定计划，完成实际暂存及装车扫描后提交派发。" description="只读预检不授权派发。派发提交会在事务中重验版本、权限及证据；未确认的业务规则仍会阻断。" />
    {errors.length>0 && <Alert type="error" message="操作阻断" description={errors.map((e,i)=><div key={i}>{e}</div>)} />}
    {mutable && <Form layout="inline" onFinish={v=>execute(`attach:${v.order_id}`,async()=>{await classifyLoadOrder(v.order_id,businessType);return attachLoadOutbounds(load.id,[v.order_id])})}>
      <Form.Item name="order_id" label="待加入订单 ID" rules={[{required:true}]}><InputNumber min={1} precision={0}/></Form.Item>
      <Button htmlType="submit" disabled={!editable || action.isPending}>明确为{businessType==='FBA'?'FBA':'私仓'}并加入</Button>
    </Form>}
    <Table size="small" pagination={false} rowKey="id" dataSource={load.outbounds??[]} columns={[{title:'订单',dataIndex:'ob_no'},{title:'订单 ID',dataIndex:'id'},{title:'客户 ID',dataIndex:'customer_id'},{title:'业务',dataIndex:'dispatch_business_type'}]}/>
    <Form layout="vertical" onFinish={v=>{const key=JSON.stringify(['allocation',v]);execute(key,()=>writeLoadAllocation(load.id,{...v,operation_id:op(key)}))}}>
      <Form.Item name="inventory_allocation_id" label="已有库存预留" rules={[{required:true}]}><Select disabled={!editable} options={reservations.map(a=>({value:a.id,label:`${a.order.ob_no} · 预留 #${a.id} · ${a.pallet_qty} PLT / ${a.carton_qty} CTN`}))}/></Form.Item>
      <Space><Form.Item name="pallet_qty" label="托盘数量" initialValue={0}><InputNumber min={0}/></Form.Item><Form.Item name="carton_qty" label="箱数量" initialValue={0}><InputNumber min={0}/></Form.Item><Button htmlType="submit" disabled={!editable || action.isPending}>保存派车分配</Button></Space>
    </Form>
    <Table size="small" pagination={false} rowKey="id" dataSource={facts.data??[]} columns={[{title:'分配 ID',dataIndex:'id'},{title:'库存预留 ID',dataIndex:'inventory_allocation_id'},{title:'PLT',dataIndex:'pallet_qty'},{title:'CTN',dataIndex:'carton_qty'}]}/>
    <Typography.Text>当前计划：{plan?`v${plan.version} · ${plan.status} · 修订 ${plan.content_revision}`:'未创建'}；计划行数 {plan?.lines.length??0}</Typography.Text>
    <Typography.Text type="secondary">锁定计划不可修改；创建下一版草稿后，旧版本审批不能授权新计划。新版本仍须满足完整分配约束，并重新取得有效核验与审批证据。</Typography.Text>
    {plan && <PlanLinesEditor key={`${plan.id}:${plan.content_revision}`} plan={plan} editable={editable} busy={action.isPending} onSave={lines=>execute('plan-edit',()=>writeLoadPlanLines(load.id,plan,lines))}/>}
    <Space wrap>
      <Button disabled={!mutable || action.isPending} onClick={()=>execute('plan-create',()=>createLoadPlan(load.id))}>{plan?.status==='FINAL'?'创建下一版草稿计划':'创建草稿计划'}</Button>
      <Button disabled={!editable || !plan || !facts.data?.length || action.isPending} onClick={()=>execute('plan-lines',()=>replaceLoadPlanLines(load.id,plan!,facts.data!))}>将全部分配写入计划</Button>
      <Button disabled={!editable || !plan?.lines.length || action.isPending} onClick={()=>execute('plan-final',()=>finalizeLoadPlan(load.id,plan!))}>校验并锁定计划</Button>
      <Button disabled={!mutable || load.status!=='PLANNED' || action.isPending} onClick={()=>execute('ready',()=>updateLoadStatus(load.id,{status:'READY'}))}>转为待派发</Button>
    </Space>
    <Typography.Title level={5}>实际暂存与装车核验</Typography.Title>
    <Typography.Text type="secondary">填写已完成拣货的实际明细 ID 与位置；服务端核对归属及数量。当前核验批次：{execution.data?.current_verification_run?.id??'未开始'}（{execution.data?.current_verification_run?.status==='COMPLETE'?'已完成':run?'进行中':'未开始'}）</Typography.Text>
    <Form form={stageForm} layout="inline">
      <Form.Item name="outbound_id" label="订单 ID" rules={[{required:true}]}><InputNumber min={1} precision={0}/></Form.Item>
      <Form.Item name="picking_item_id" label="拣货明细 ID" rules={[{required:true}]}><InputNumber min={1} precision={0}/></Form.Item>
      <Form.Item name="staging_location_id" label="暂存位置 ID" rules={[{required:true}]}><InputNumber min={1} precision={0}/></Form.Item>
      <Form.Item name="quantity" label="实测数量" rules={[{required:true}]}><InputNumber min={0}/></Form.Item>
      <Form.Item name="quantity_unit" initialValue="PALLET"><Select options={[{value:'PALLET',label:'托盘'},{value:'CARTON',label:'箱'}]}/></Form.Item>
    </Form>
    <Space wrap>
      <Button disabled={!mutable || action.isPending} onClick={()=>void saveExecution('stage').catch(e=>setErrors(dispatchFailure(e)))}>记录暂存</Button>
      <Button disabled={!mutable || executionBusy || action.isPending} onClick={()=>execute('verify-start',()=>writeLoadExecution(load.id,'verify/start',{client_operation_id:op('verify-start')}))}>开始核验</Button>
      <Button disabled={!mutable || !run || executionBusy || action.isPending} onClick={()=>void saveExecution('verify/scan').catch(e=>setErrors(dispatchFailure(e)))}>记录装车扫描</Button>
      <Button disabled={!mutable || !run || executionBusy || action.isPending} onClick={()=>execute(`complete:${run}`,()=>writeLoadExecution(load.id,'verify/complete',{verification_run_id:run,client_operation_id:op(`complete:${run}`)}))}>核对数量并完成核验</Button>
    </Space>
    <Typography.Text>暂存：{String(execution.data?.staged_quantity??'未知')}；装车核验：{execution.data?.verification_complete?'已完成':'未完成'}；指纹一致：{execution.data?.manifest_matches?'是':'否'}</Typography.Text>
    <LoadDispatchEvidence load={load} canManage={canManage} onChanged={()=>{setErrors([]);onChanged?.()}}/>
    <Button type="primary" disabled={!mutable || load.status!=='READY' || plan?.status!=='FINAL' || action.isPending} onClick={()=>{const key=`dispatch:${plan!.id}:${plan!.content_revision}`;execute(key,()=>updateLoadStatus(load.id,dispatchRequest(plan!,op(key))))}}>提交实际派发（事务内重验）</Button>
    {(facts.isError || plans.isError || execution.isError) && <Alert type="error" message="证据读取失败，请刷新后重试"/>}
  </Space>
}
