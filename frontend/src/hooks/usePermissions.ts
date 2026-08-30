import { useQuery } from '@tanstack/react-query'
import { getCurrentUser, UserPermission } from '../api/auth'

export function useCurrentUser() {
  return useQuery({ queryKey: ['current-user'], queryFn: getCurrentUser, staleTime: 5 * 60_000 })
}

export function usePermission(permission: UserPermission) {
  const currentUser = useCurrentUser()
  return { ...currentUser, allowed: currentUser.data?.permissions.includes(permission) ?? false }
}
