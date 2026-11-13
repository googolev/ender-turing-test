import type { ComponentProps } from "react"

import type { UserRole } from "@/client"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Admin",
  manager: "Manager",
  member: "Member",
}

export const ROLES = [
  "admin",
  "manager",
  "member",
] as const satisfies readonly UserRole[]

type RoleSelectProps = {
  value: UserRole | undefined
  onValueChange: (role: UserRole) => void
} & Omit<ComponentProps<typeof SelectTrigger>, "children">

// Remaining props (id, aria-*) go to the trigger, so it can sit inside
// <FormControl> and be labelled by the form field's <FormLabel>.
export function RoleSelect({
  value,
  onValueChange,
  ...triggerProps
}: RoleSelectProps) {
  return (
    <Select
      value={value}
      onValueChange={(role) => onValueChange(role as UserRole)}
    >
      <SelectTrigger className="w-full" {...triggerProps}>
        <SelectValue placeholder="Select a role" />
      </SelectTrigger>
      <SelectContent>
        {ROLES.map((role) => (
          <SelectItem key={role} value={role}>
            {ROLE_LABELS[role]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
