import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { login } from '../api/auth';
import { useAuthStore } from '../stores/auth';
import '../login-cyberpunk.css';

export function LoginPage() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const setTokens = useAuthStore((state) => state.setTokens);

  async function submit(values: { username: string; password: string }) {
    setLoading(true);
    setError('');
    try {
      const tokens = await login(values.username, values.password);
      setTokens(tokens.access_token, tokens.refresh_token);
    } catch {
      setError('Invalid username/password or backend unavailable.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-grid" aria-hidden="true" />
      <div className="login-aurora" aria-hidden="true" />
      <div className="login-stars" aria-hidden="true">
        {Array.from({ length: 18 }, (_, index) => <i key={index} />)}
      </div>
      <div className="login-hud login-hud-left" aria-hidden="true">
        <span>NODE // LAX-07</span>
        <b>34.0522° N</b>
        <small>LINK STABLE</small>
      </div>
      <div className="login-hud login-hud-right" aria-hidden="true">
        <span>DLX CORE</span>
        <b>SYS 03</b>
        <small>ENCRYPTED</small>
      </div>
      <div className="login-panel">
        <div className="login-panel-corners" aria-hidden="true" />
        <div className="login-wear" aria-hidden="true" />
        <div className="login-signal" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <h1 className="login-title" data-text="DLX YUKI WMS" aria-label="DLX YUKI WMS">
          <span data-text="DLX YUKI">DLX <i className="neon-weak">Y</i>UKI</span>
          <span data-text="WMS">WM<i className="neon-weak">S</i></span>
        </h1>
        <div className="login-kicker"><span>WAREHOUSE OPERATING SYSTEM</span><b>V3.0</b></div>
        <Typography.Title level={3}>SYSTEM ACCESS</Typography.Title>
        {error && <Alert type="error" message={error} showIcon />}
        <Form layout="vertical" onFinish={submit}>
          <Form.Item name="username" label="USERNAME" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="PASSWORD" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button className="login-submit" type="primary" htmlType="submit" loading={loading} block>
            INITIALIZE SESSION
          </Button>
        </Form>
        <div className="login-meta" aria-hidden="true"><span>AUTH / 256</span><span>UPLINK / 99.98%</span></div>
        <div className="login-status"><i /> SECURE TERMINAL ONLINE</div>
      </div>
      <div className="login-footer" aria-hidden="true">DLX INDUSTRIAL INTELLIGENCE NETWORK <span>•</span> AUTHORIZED ACCESS ONLY</div>
    </div>
  );
}
