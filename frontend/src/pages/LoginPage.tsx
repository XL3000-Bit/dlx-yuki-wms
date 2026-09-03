import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Typography } from 'antd';
import { useState } from 'react';
import { login } from '../api/auth';
import { useAuthStore } from '../stores/auth';
import '../login-original.css';

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
    <div className="login-page-original">
      <div className="login-panel-original">
        <div className="login-brand-original">DLX <span>Yuki WMS V3</span></div>
        <Typography.Title level={3}>Warehouse Sign In</Typography.Title>
        {error && <Alert type="error" message={error} showIcon />}
        <Form layout="vertical" onFinish={submit}>
          <Form.Item name="username" label="Username" rules={[{ required: true }]}>
            <Input prefix={<UserOutlined />} />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            Sign In
          </Button>
        </Form>
      </div>
    </div>
  );
}
