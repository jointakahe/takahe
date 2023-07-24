from users.models import Domain


class DomainService:
    """
    High-level domain handling methods
    """

    @classmethod
    def block(cls, domains: list[str]) -> None:
        domains_to_block = Domain.objects.filter(domain__in=domains)
        domains_to_block.update(blocked=True)

        already_blocked = domains_to_block.values_list("domain", flat=True)
        domains_to_create = []
        for domain in domains:
            if domain not in already_blocked:
                domains_to_create.append(
                    Domain(domain=domain, blocked=True, local=False)
                )

        Domain.objects.bulk_create(domains_to_create)
