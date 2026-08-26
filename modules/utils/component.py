def _children(node):
    for attr in ('children', 'components'):
        for child in getattr(node, attr, None) or ():
            yield child
    accessory = getattr(node, 'accessory', None)
    if accessory is not None:
        yield accessory
    inner = getattr(node, 'component', None)
    if inner is not None:
        yield inner


class Component:
    @staticmethod
    def walk(node):
        for child in _children(node):
            yield child
            yield from Component.walk(child)

    @staticmethod
    def descendants(message):
        for component in getattr(message, 'components', None) or []:
            yield from Component.walk(component)

    @staticmethod
    def text(node):
        parts = []
        content = getattr(node, 'content', None)
        if content:
            parts.append(content)
        for child in _children(node):
            parts.append(Component.text(child))
        return '\n'.join(part for part in parts if part)

    @staticmethod
    def buttons(message):
        for component in Component.descendants(message):
            if hasattr(component, 'click'):
                yield component