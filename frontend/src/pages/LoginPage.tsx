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
    <main className="login-page-original">
      <section className="login-panel-original" aria-labelledby="login-title">
        <div className="login-brand-original">
          <span>Warehouse Management System</span>
        </div>
        <Typography.Title id="login-title" level={1}>Warehouse Sign In</Typography.Title>
        {error && <Alert type="error" message={error} showIcon />}
        <Form layout="vertical" size="large" onFinish={submit}>
          <Form.Item name="username" label="Username" rules={[{ required: true, message: 'Please enter your username.' }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" autoCapitalize="none" spellCheck={false} />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Please enter your password.' }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            Sign In
          </Button>
        </Form>
      </section>
    </main>
  );
}
