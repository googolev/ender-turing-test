import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { redirect, useNavigate } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type Permission,
  type UserMePublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

const isLoggedIn = () => {
  return localStorage.getItem("access_token") !== null
}

// The backend derives permissions from the user's role; the UI only checks them.
const hasPermission = (
  user: UserMePublic | null | undefined,
  permission: Permission,
) => user?.permissions.includes(permission) ?? false

// For a route's beforeLoad. Reads the user fresh rather than from the cache,
// so a role changed by an admin applies on the next navigation.
const requirePermission = async (permission: Permission) => {
  const { data: user } = await UsersService.readUserMe()
  if (!hasPermission(user, permission)) {
    throw redirect({ to: "/" })
  }
}

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data: user } = useQuery<UserMePublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: async () => (await UsersService.readUserMe()).data,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ body: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const login = async (data: AccessToken) => {
    const response = await LoginService.loginAccessToken({
      body: data,
    })
    localStorage.setItem("access_token", response.data.access_token)
  }

  const loginMutation = useMutation({
    mutationFn: login,
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: handleError.bind(showErrorToast),
  })

  const logout = () => {
    localStorage.removeItem("access_token")
    navigate({ to: "/login" })
  }

  const can = (permission: Permission) => hasPermission(user, permission)

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
    can,
  }
}

export { isLoggedIn, requirePermission }
export default useAuth
