"use client";
import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  BindingsPanel,
  type AccessAuthority,
} from "@/components/admin/access-bindings";
import {
  AttributesPanel,
  PoliciesPanel,
  PrincipalsPanel,
  ResourcesPanel,
} from "@/components/admin/access-panels";
import { useAuthStore } from "@/lib/store/auth";

/**
 * Admin → Acesso (spec 0018 §4.6, CA11): one page for every grant, platform
 * (0014) and engines (0009), plus the 0009 conditions and trusted attributes.
 * Each tab and action shows only for the authority of its family; the API
 * authorizes every call again.
 */
export default function AccessPage() {
  const user = useAuthStore((s) => s.user);
  const bootstrap = !!(user?.bootstrap ?? user?.is_admin);
  const held = new Set(user?.permissions ?? []);
  const enginesOn = !!user?.engine_access_enabled;
  const authority: AccessAuthority = {
    bootstrap,
    held,
    platformRead: bootstrap || held.has("iam.bindings.read"),
    platformManage: bootstrap || held.has("iam.bindings.manage"),
    enginesManage: enginesOn && (bootstrap || held.has("access.grants.manage")),
  };
  const enginesBootstrap = enginesOn && bootstrap;
  const tabs = [
    {
      key: "concessoes",
      label: "Concessões",
      show: authority.platformRead || authority.enginesManage,
      body: <BindingsPanel authority={authority} />,
    },
    {
      key: "politicas",
      label: "Políticas",
      show: authority.enginesManage,
      body: <PoliciesPanel />,
    },
    {
      key: "atributos",
      label: "Atributos de engine",
      show: enginesBootstrap,
      body: <AttributesPanel />,
    },
    {
      key: "recursos",
      label: "Recursos",
      show: enginesBootstrap,
      body: <ResourcesPanel />,
    },
    {
      key: "principais",
      label: "Principais de instalação",
      show: enginesBootstrap,
      body: <PrincipalsPanel />,
    },
  ].filter((t) => t.show);
  const [tab, setTab] = useState("concessoes");
  const current = tabs.some((t) => t.key === tab) ? tab : tabs[0]?.key;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Acesso</h2>
        <p className="text-muted-foreground">
          Toda concessão é um binding com validade UTC de no máximo 365 dias.
          Papéis de plataforma concedem administração entre usuários
          (estatísticas, recuperação de jobs, routing, auditoria) e o uso de
          engines remotas; papéis de engines fixam uma revisão de política como
          condição, e uma ação precisa atender integralmente uma concessão.
        </p>
        <p className="text-sm mt-2">
          As duas famílias não se enxergam: um papel de plataforma não abre
          engines nem perfis de execução. O bootstrap da plataforma não aparece
          aqui. Administrador de acesso não recebe execução nem credenciais
          pelo seu papel.
        </p>
      </div>
      {!enginesOn && (bootstrap || held.has("access.grants.manage")) && (
        <p role="status" className="text-sm rounded-md border bg-muted/40 p-3">
          Concessões de engines requerem a migração 0009 e IAM_MODE=enforce (ou
          ENGINE_ACCESS_ENABLED=true).
        </p>
      )}
      {current ? (
        <Tabs value={current} onValueChange={setTab}>
          <TabsList className="h-auto flex-wrap justify-start">
            {tabs.map((t) => (
              <TabsTrigger key={t.key} value={t.key}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((t) => (
            <TabsContent key={t.key} value={t.key} className="mt-6">
              {t.body}
            </TabsContent>
          ))}
        </Tabs>
      ) : (
        <p className="text-sm text-muted-foreground">
          Nenhuma seção de acesso disponível para o seu usuário.
        </p>
      )}
    </div>
  );
}
