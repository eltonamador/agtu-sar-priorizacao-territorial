# Parecer de reauditoria — RURAL-01 MOV-V v2

## Veredito

**Apto para fechamento T4, condicionado à emissão e verificação do ledger final.**

Não foi identificada falha aritmética que invalide o processamento. A implementação final preserva as duas hipóteses BASE sem seleção automática, mantém a posição verdadeira fora da execução e registra o custo como medida relativa de esforço, não como tempo, probabilidade ou localização prevista.

## Não conformidades corrigidas antes do congelamento

1. O firewall passou a examinar recursivamente chaves, valores textuais e caminhos, além de validar os controles cegos e os aliases proibidos.
2. A hipótese `H_REDE_DISPONIVEL__BASE` deixou de ser escolha implícita. Ela permanece apenas como referência técnica explicitamente não selecionada; os resultados das duas hipóteses BASE são apresentados em paralelo.
3. A suíte passou a cobrir barreira com abertura, preferência de corredor, ausência de WorldCover, tentativas de contornar o firewall, empate no corte de classificação e adulteração de manifesto.
4. Cada corredor passou a registrar hipótese, perfil, algoritmo, células inicial e final, extensão geométrica, regra de destino e hash da configuração.
5. A configuração e as saídas passaram a ser vinculadas a recibo verificável da suíte e a controle de integridade do manifesto.

## Evidências finais

- 21 testes aprovados, sem falhas ou erros;
- 37 de 37 portas de qualidade aprovadas;
- firewall aprovado na execução integral;
- 28 arquivos do manifesto principal verificados;
- oito arquivos centrais reproduzidos byte a byte em segunda execução;
- 29 arquivos selados da v1 preservados;
- deduplicação de 132 células com sobreposição entre hidrografia e classes aquáticas/úmidas;
- posição verdadeira não consultada nem representada;
- tempo de 14 horas conservado como contexto, sem conversão automática.

## Limites do parecer

O parecer certifica coerência interna, rastreabilidade, determinismo e cumprimento do protocolo cego. Não certifica eficácia operacional, calibração dos multiplicadores, transitabilidade do sub-bosque ou generalização para outros cenários. O resultado permanece `REVISAR` para uso interpretativo e exige confronto posterior com a referência congelada, sem reajuste dos parâmetros.
