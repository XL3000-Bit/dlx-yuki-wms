import { BellOutlined, CheckOutlined } from "@ant-design/icons";
import { Badge, Button, Drawer, Empty, List, Space, Spin, Tag, Typography, Alert } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

type Notice={id:number;type:string;severity:string;title:string;message:string;reference:string;target_route:string;is_read:boolean;created_at:string};
const colors:Record<string,string>={INFO:"blue",WARNING:"gold",HIGH:"orange",CRITICAL:"red"};

export function NotificationCenter(){
  const [open,setOpen]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(""),[items,setItems]=useState<Notice[]>([]),[count,setCount]=useState(0);
  const nav=useNavigate();
  const loadCount=()=>api.get<{count:number}>("/notifications/unread-count").then(r=>setCount(r.data.count)).catch(()=>setCount(0));
  const load=async()=>{setLoading(true);setError("");try{const r=await api.get<{data:Notice[]}>("/notifications",{params:{unread_only:true,per_page:50}});setItems(r.data.data);setCount(r.data.data.length)}catch{setError("Notifications could not be loaded.")}finally{setLoading(false)}};
  useEffect(()=>{void loadCount()},[]);
  useEffect(()=>{if(open)void load()},[open]);
  const visit=async(n:Notice)=>{await api.post(`/notifications/${n.id}/read`);setOpen(false);nav(n.target_route);void loadCount()};
  const markAll=async()=>{await api.post("/notifications/mark-all-read");setItems([]);setCount(0)};
  return <>
    <Badge count={count} overflowCount={99} size="small"><Button aria-label="Notifications" icon={<BellOutlined/>} onClick={()=>setOpen(true)}/></Badge>
    <Drawer title="Operational notifications" open={open} onClose={()=>setOpen(false)} width={420}
      extra={<Button size="small" icon={<CheckOutlined/>} disabled={!items.length} onClick={markAll}>Mark all read</Button>}>
      {loading?<Spin/>:error?<Alert type="error" message={error} showIcon/>:items.length===0?<Empty description="No unread notifications"/>:
      <List dataSource={items} renderItem={n=>(
        <List.Item onClick={()=>void visit(n)} style={{cursor:"pointer"}}>
          <List.Item.Meta title={<Space><Tag color={colors[n.severity]}>{n.severity}</Tag><Typography.Text strong>{n.title}</Typography.Text></Space>}
            description={<><div>{n.message}</div><Typography.Text type="secondary">{n.reference} · {new Date(n.created_at).toLocaleString()}</Typography.Text></>}/>
        </List.Item>
      )}/>
      }
      <Button block type="link" onClick={()=>void load()}>View all / refresh</Button>
    </Drawer>
  </>
}
