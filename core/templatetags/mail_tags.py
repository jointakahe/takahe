from django.template import Library, Template

register = Library()


@register.inclusion_tag("emails/_body_content.html", takes_context=True)
def email_body_content(context, content):
    template = Template(content)
    return {"content": template.render(context)}


@register.inclusion_tag("emails/_button.html", takes_context=True)
def email_button(context, button_text, button_link):
    text_template = Template(button_text)
    link_template = Template(button_link)
    return {
        "button_text": text_template.render(context),
        "button_link": link_template.render(context),
    }


@register.inclusion_tag("emails/_footer.html", takes_context=True)
def email_footer(context, content):
    template = Template(content)
    return {"content": template.render(context)}
